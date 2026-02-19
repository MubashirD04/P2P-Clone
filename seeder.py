import socket
import threading
import time
import os
import logging
import hashlib
import argparse
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    filename="seeder_logs.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Global settings
SEEDER_IP = "localhost"
SEEDER_PORT = 6002  # Default port
TRACKER_IP = "localhost"
TRACKER_PORT = 5000
CHUNK_SIZE = 512 * 1024  # 512 KB

# Global variables
registered_files = set()
file_hashes = {}  # {filename: {chunk_index: hash_value}}
file_progress = {}  # {filename: {"total": int, "served": int, "pbar": tqdm_obj}}
progress_lock = threading.Lock()  # Lock for thread-safe progress bar updates
current_transfers = {}  # Track active transfers to prevent duplicate progress bars

def print_startup_banner(port):
    """Print a clear startup banner at the top of the terminal"""
    print("\n" + "="*70)
    print(f"🚀 P2P File Seeder - Started on {SEEDER_IP}:{port}")
    print(f"📡 Connected to tracker at {TRACKER_IP}:{TRACKER_PORT}")
    print("🔍 Scanning for files to seed...")
    print("="*70 + "\n")

def calculate_chunk_hash(filename, chunk_index):
    """Calculate SHA-256 hash of a file chunk"""
    if filename not in file_hashes:
        file_hashes[filename] = {}
        file_size = os.path.getsize(filename)
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        with open(filename, "rb") as f:
            for idx in range(total_chunks):
                f.seek(idx * CHUNK_SIZE)
                data = f.read(CHUNK_SIZE)
                file_hashes[filename][idx] = hashlib.sha256(data).hexdigest()
    
    return file_hashes[filename].get(chunk_index)

def register_with_tracker(filename, port):
    """Register a file with the tracker server"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tracker_socket:
            tracker_socket.settimeout(5)
            message = f"REGISTER {filename} {port}"
            tracker_socket.sendto(message.encode(), (TRACKER_IP, TRACKER_PORT))
            
            try:
                response, _ = tracker_socket.recvfrom(1024)
                response_text = response.decode()
                
                if response_text.startswith("REGISTERED") and filename not in registered_files:
                    registered_files.add(filename)
                    logging.info(f"✅ Registered {filename} with tracker")
                    print(f"✅ Registered: {filename}")
                    return True
            except socket.timeout:
                logging.warning(f"⚠️ No response from tracker when registering {filename}")
        
        return False
    except Exception as e:
        logging.error(f"❌ Registration error: {str(e)}")
        return False

def send_heartbeat():
    """Send periodic heartbeats to tracker"""
    heartbeat_failures = 0
    max_failures = 3  # Shutdown after 3 consecutive failures
    
    while True:
        time.sleep(10)
        for filename in registered_files.copy():
            if not os.path.exists(filename):
                registered_files.remove(filename)
                logging.warning(f"⚠️ Removed non-existent file: {filename}")
                continue

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tracker_socket:
                    tracker_socket.sendto(f"HEARTBEAT {filename}".encode(), (TRACKER_IP, TRACKER_PORT))
                    logging.info(f"💓 Sent heartbeat for {filename}")
                    heartbeat_failures = 0  # Reset on success
            except Exception as e:
                heartbeat_failures += 1
                logging.error(f"⚠️ Heartbeat failed: {str(e)}")
                if heartbeat_failures >= max_failures:
                    print("🚨 Tracker unreachable. Shutting down seeder...")
                    os._exit(1)

def handle_shutdown_listener(port):
    """Listen for UDP shutdown commands"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        try:
            udp_socket.bind((SEEDER_IP, port))
            
            while True:
                data, addr = udp_socket.recvfrom(1024)
                if data == b"SHUTDOWN":
                    print("🛑 Received shutdown command via UDP. Exiting...")
                    logging.info("🛑 Received shutdown command via UDP. Exiting...")
                    os._exit(0)
        except Exception as e:
            logging.error(f"UDP shutdown listener error: {str(e)}")

def handle_leecher(client_socket, port):
    """Handle requests from a leecher"""
    try:
        request = client_socket.recv(1024).decode().strip()
        
        # Handle shutdown request
        if request == "SHUTDOWN":
            logging.info("🛑 Received shutdown request from leecher")
            print("🛑 Shutdown request received from leecher. Closing seeder...")
            client_socket.close()
            os._exit(0)
        
        # Handle filesize request
        if request.startswith("FILESIZE "):
            filename = request.split()[1]
            if os.path.exists(filename):
                # Register file with the tracker
                register_with_tracker(filename, port)
                file_size = os.path.getsize(filename)
                client_socket.sendall(str(file_size).encode())
                logging.info(f"📤 Sent size for {filename}: {file_size} bytes")
            else:
                client_socket.sendall(b"ERROR: File not found")
                logging.error(f"❌ File not found: {filename}")
            return
        
        # Handle chunk request
        if request.startswith("REQUEST "):
            parts = request.split()
            if len(parts) != 3:
                client_socket.sendall(b"ERROR: Invalid request")
                return

            filename = parts[1]
            chunk_index = int(parts[2])

            if not os.path.exists(filename):
                client_socket.sendall(b"ERROR: File not found")
                return

            file_size = os.path.getsize(filename)
            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

            if chunk_index < 0 or chunk_index >= total_chunks:
                client_socket.sendall(b"ERROR: Invalid chunk")
                return

            # Initialize progress tracking for this file
            with progress_lock:
                # Determine if we should create a new progress bar
                create_new_pbar = False
                
                if filename not in file_progress:
                    create_new_pbar = True
                elif file_progress[filename]["served"] >= file_progress[filename]["total"]:
                    # First chunk of a new transfer - reset the counter without creating a new bar
                    file_progress[filename]["served"] = 0
                    create_new_pbar = False
                
                if create_new_pbar:
                    # Create a new progress bar for this file
                    file_progress[filename] = {
                        "total": total_chunks,
                        "served": 0,
                        "pbar": tqdm(
                            total=total_chunks,
                            desc=f"Serving {os.path.basename(filename)}",
                            unit="chunk"
                        )
                    }

            # Read the chunk data
            start_pos = chunk_index * CHUNK_SIZE
            end_pos = min(start_pos + CHUNK_SIZE, file_size)
            
            with open(filename, "rb") as f:
                f.seek(start_pos)
                chunk_data = f.read(end_pos - start_pos)

            # Calculate hash for integrity verification
            chunk_hash = calculate_chunk_hash(filename, chunk_index)
            
            # Send hash followed by chunk data
            response = f"HASH {chunk_hash}\n".encode() + chunk_data
            client_socket.sendall(response)
            
            # Update progress
            with progress_lock:
                if filename in file_progress:
                    # Check if we need to update the progress bar
                    if file_progress[filename]["pbar"] is not None:
                        file_progress[filename]["served"] += 1
                        file_progress[filename]["pbar"].update(1)
                    
                    # If we've served all chunks, mark the file as complete but don't close the bar
                    if file_progress[filename]["served"] >= file_progress[filename]["total"]:
                        logging.info(f"✅ Completed serving {filename}")
            
            logging.info(f"✅ Sent chunk {chunk_index} of {filename}")
    except Exception as e:
        logging.error(f"❌ Error handling leecher: {str(e)}")
    finally:
        client_socket.close()

def cleanup_progress_bars():
    """Periodically clean up completed progress bars"""
    while True:
        time.sleep(5)
        with progress_lock:
            for filename in list(file_progress.keys()):
                if file_progress[filename]["served"] >= file_progress[filename]["total"]:
                    if file_progress[filename]["pbar"] is not None:
                        # Don't close the bar, just prevent further updates
                        file_progress[filename]["pbar"] = None

def register_available_files(port):
    """Register all files in the downloads directory and current directory with the tracker"""
    files = []
    
    # Check downloads directory
    downloads_dir = "downloads"
    if os.path.exists(downloads_dir) and os.path.isdir(downloads_dir):
        for filename in os.listdir(downloads_dir):
            full_path = os.path.join(downloads_dir, filename)
            if os.path.isfile(full_path) and not filename.endswith(('.py', '.txt', '.log')):
                files.append(full_path)
    
    # Check current directory
    for filename in os.listdir('.'):
        if os.path.isfile(filename) and not filename.endswith(('.py', '.txt', '.log')):
            files.append(filename)
    
    if not files:
        print("⚠️ No files found to seed!")
        return
    
    print(f"📁 Found {len(files)} files to seed:")
    for filename in files:
        register_with_tracker(filename, port)

def start_seeder(port):
    """Start the seeder server"""
    # Print startup banner
    print_startup_banner(port)
    
    # Register available files
    register_available_files(port)
    
    # Start heartbeat thread
    threading.Thread(target=send_heartbeat, daemon=True).start()
    
    # Start shutdown listener thread for UDP commands
    threading.Thread(target=handle_shutdown_listener, args=(port,), daemon=True).start()
    
    # Start TCP server for leecher connections
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as seeder_socket:
        seeder_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        seeder_socket.bind((SEEDER_IP, port))
        seeder_socket.listen(5)
        
        print(f"\n🟢 Seeder ready and listening on port {port}")
        print("⏳ Waiting for download requests...")
        
        try:
            while True:
                client, addr = seeder_socket.accept()
                threading.Thread(target=handle_leecher, args=(client, port)).start()
        except KeyboardInterrupt:
            print("\n🛑 Seeder shutting down...")
            # Close all active progress bars
            with progress_lock:
                for filename in list(file_progress.keys()):
                    if file_progress[filename]["pbar"] is not None:
                        file_progress[filename]["pbar"].close()
        finally:
            logging.info("Seeder shutting down")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="P2P File Sharing Seeder")
    parser.add_argument("-p", "--port", type=int, default=SEEDER_PORT,
                      help=f"Port to run the seeder on (default: {SEEDER_PORT})")
    args = parser.parse_args()
    
    # Start the seeder with the specified port
    start_seeder(args.port)