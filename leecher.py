import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import socket
import threading
import time
import os
import logging
import hashlib
import sys
import subprocess
from threading import Semaphore

logging.basicConfig(
    filename="leecher_logs.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

LEECHER_IP = "localhost"
TRACKER_IP = "localhost"
TRACKER_PORT = 5000
MAX_RETRIES = 5
CHUNK_SIZE = 512 * 1024  # 512 KB as specified in the assignment
DEFAULT_SEEDER_PORT = 6002

class LeecherUI:
    def __init__(self, master):
        self.master = master
        master.title("P2P File Leecher")
        
        # Override the destroy method
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.frame = ttk.Frame(master, padding="10")
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(self.frame, text="File name:").grid(row=0, column=0, sticky="w")
        self.filename_entry = ttk.Entry(self.frame, width=30)
        self.filename_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.check_btn = ttk.Button(self.frame, text="Check Availability", command=self.check_file)
        self.check_btn.grid(row=1, column=0, pady=5, sticky="w")
        
        self.download_btn = ttk.Button(self.frame, text="Download", state="disabled", command=self.start_download)
        self.download_btn.grid(row=1, column=1, pady=5, sticky="w")
        
        self.reseed_btn = ttk.Button(self.frame, text="Reseed Files", command=self.reseed_files)
        self.reseed_btn.grid(row=1, column=2, pady=5, sticky="w")
        
        # Add active seeders label
        ttk.Label(self.frame, text="Active Seeders:").grid(row=2, column=0, sticky="w")
        self.active_seeders_label = ttk.Label(self.frame, text="0")
        self.active_seeders_label.grid(row=2, column=1, sticky="w")
        
        self.file_info = ttk.Label(self.frame, text="")
        self.file_info.grid(row=3, columnspan=3, sticky="w")
        
        self.progress_frame = ttk.LabelFrame(self.frame, text="Download Progress")
        self.progress_frame.grid(row=4, columnspan=3, pady=5, sticky="ew")
        
        self.progress = ttk.Progressbar(self.progress_frame, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(fill=tk.X, padx=5, pady=5)
        
        self.chunk_label = ttk.Label(self.progress_frame, text="")
        self.chunk_label.pack(pady=2)
        
        self.status = ttk.Label(self.frame, text="Status: Idle")
        self.status.grid(row=5, columnspan=3, sticky="w")
        
        self.file_size = 0
        self.total_chunks = 0
        self.downloaded_chunks = 0
        self.current_file = ""
        self.download_speed = 0
        self.active_seeders = 0
        
        # Add a list to track completed downloads for reseeding
        self.completed_downloads = []
        # Dict to track chunk hashes
        self.chunk_hashes = {}

    def on_close(self):
        """Handle window close event"""
        self.notify_shutdown()
        self.master.destroy()

    def notify_shutdown(self):
        """Notify tracker and seeders to shut down"""
        try:
            # Notify tracker
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tracker_socket:
                tracker_socket.sendto(b"SHUTDOWN", (TRACKER_IP, TRACKER_PORT))
            
            # Notify seeders (if any)
            if hasattr(self, 'current_file') and self.current_file:
                seeders = self.request_seeders(self.current_file)
                for ip, port in seeders:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as seeder_socket:
                            seeder_socket.connect((ip, int(port)))
                            seeder_socket.send(b"SHUTDOWN")
                    except Exception as e:
                        logging.error(f"Error notifying seeder {ip}:{port}: {str(e)}")
        except Exception as e:
            logging.error(f"Error during shutdown notification: {str(e)}")

    def check_file(self):
        """Check for file availability from seeders"""
        filename = self.filename_entry.get().strip()
        if not filename:
            messagebox.showerror("Error", "Please enter a filename")
            return
        
        self.status.config(text="Status: Checking availability...")
        threading.Thread(target=self.do_check_file, args=(filename,)).start()

    def do_check_file(self, filename):
        """Background thread to check file availability"""
        try:
            file_size = self.get_file_size(filename)
            if file_size:
                self.file_size = file_size
                self.total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
                self.current_file = filename
                
                self.master.after(0, self.update_file_info, filename, file_size)
                self.master.after(0, self.status.config, {"text": "Status: File available!"})
                self.master.after(0, self.download_btn.config, {"state": "normal"})
            else:
                self.master.after(0, messagebox.showwarning, "Not Found", "File not available")
                self.master.after(0, self.status.config, {"text": "Status: File unavailable"})
        except Exception as e:
            logging.error(f"Error checking file: {str(e)}")
            self.master.after(0, messagebox.showerror, "Error", str(e))

    def get_file_size(self, filename):
        """Get file size from available seeders"""
        seeders = self.request_seeders(filename, retry=True)
        if seeders:
            self.active_seeders = len(seeders)
            self.master.after(0, self.active_seeders_label.config, {"text": str(self.active_seeders)})
            return self.try_get_filesize(seeders, filename)
        
        self.active_seeders = 0
        self.master.after(0, self.active_seeders_label.config, {"text": "0"})
        return None

    def request_seeders(self, filename, retry=False):
        """Request list of seeders from tracker"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(f"REQUEST {filename}".encode(), (TRACKER_IP, TRACKER_PORT))
            try:
                sock.settimeout(2)
                resp = sock.recv(1024).decode()
                if resp.startswith("SEEDERS"):
                    seeders = [tuple(s.split(":")) for s in resp.split()[1:]]
                    logging.info(f"Got {len(seeders)} seeders for {filename}")
                    return seeders
                logging.warning(f"Tracker response: {resp}")
            except socket.timeout:
                logging.warning(f"Tracker request timed out for {filename}")
                if retry:
                    return self.try_default_seeder(filename)
            except Exception as e:
                logging.error(f"Error requesting seeders: {str(e)}")
        return []

    def try_default_seeder(self, filename):
        """Try to get file size from default seeder"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect(("127.0.0.1", DEFAULT_SEEDER_PORT))
                sock.send(f"FILESIZE {filename}".encode())
                size = sock.recv(1024).decode()
                if size.isdigit():
                    logging.info(f"Got file size from default seeder: {size} bytes")
                    self.active_seeders = 1
                    self.master.after(0, self.active_seeders_label.config, {"text": "1"})
                    return int(size)
                logging.warning(f"Invalid file size response: {size}")
        except Exception as e:
            logging.error(f"Error connecting to default seeder: {str(e)}")
        return None

    def try_get_filesize(self, seeders, filename):
        """Try to get file size from multiple seeders"""
        for ip, port in seeders:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5)
                    sock.connect((ip, int(port)))
                    sock.send(f"FILESIZE {filename}".encode())
                    size = sock.recv(1024).decode()
                    if size.isdigit():
                        logging.info(f"Got file size from seeder {ip}:{port}: {size} bytes")
                        return int(size)
                    logging.warning(f"Invalid file size response from {ip}:{port}: {size}")
            except Exception as e:
                logging.error(f"Error connecting to seeder {ip}:{port}: {str(e)}")
        return None

    def update_file_info(self, filename, size):
        """Update UI with file information"""
        total_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        self.file_info.config(text=f"File: {filename} | Size: {size} bytes | Chunks: {total_chunks}")

    def start_download(self):
        """Begin the download process"""
        filename = self.filename_entry.get().strip()
        self.chunk_hashes = {}  # Reset chunk hashes
        self.status.config(text="Status: Starting download...")
        self.progress["value"] = 0
        self.downloaded_chunks = 0
        self.chunk_label.config(text=f"Chunks: 0/{self.total_chunks}")
        
        threading.Thread(target=self.do_download, args=(filename,)).start()

    def do_download(self, filename):
        """Background thread to handle the actual download"""
        try:
            seeders = self.request_seeders(filename)
            self.active_seeders = len(seeders)
            self.master.after(0, self.active_seeders_label.config, {"text": str(self.active_seeders)})
            
            if not seeders:
                raise Exception("No seeders available")
            
            if not self.file_size:
                self.file_size = self.try_get_filesize(seeders, filename)
            if not self.file_size:
                raise Exception("Failed to get file size")
            
            total_chunks = (self.file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
            file_parts = [None] * total_chunks
            
            # Create a download directory if it doesn't exist
            download_dir = "downloads"
            if not os.path.exists(download_dir):
                os.makedirs(download_dir)
            
            downloaded_bytes = 0
            start_time = time.time()
            
            # Download chunks in parallel
            threads = []
            max_threads = min(10, len(seeders) * 2)  # Adjust based on available seeders
            thread_semaphore = Semaphore(max_threads)
            
            for chunk in range(total_chunks):
                thread_semaphore.acquire()
                thread = threading.Thread(
                    target=self.download_chunk, 
                    args=(seeders, chunk, file_parts, filename, thread_semaphore)
                )
                thread.daemon = True
                thread.start()
                threads.append(thread)
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Check if all chunks were downloaded
            if None in file_parts:
                raise Exception("Some chunks failed to download")
            
            # Create completed file
            output_path = os.path.join(download_dir, f"{filename}")
            with open(output_path, "wb") as f:
                for chunk in file_parts:
                    f.write(chunk)
            
            elapsed_time = time.time() - start_time
            download_speed = self.file_size / elapsed_time / 1024 if elapsed_time > 0 else 0
            
            # Record this file for potential reseeding
            self.completed_downloads.append(filename)
            
            self.master.after(0, self.register_as_seeder, filename, output_path)
            self.master.after(0, self.status.config, 
                              {"text": f"Status: Download complete! Speed: {download_speed:.2f} KB/s"})
            self.master.after(0, messagebox.showinfo, "Success", 
                              f"File downloaded successfully to {output_path}")
            
        except Exception as e:
            logging.error(f"Download error: {str(e)}")
            self.master.after(0, messagebox.showerror, "Error", str(e))
            self.master.after(0, self.status.config, {"text": f"Status: Error - {str(e)}"})

    def download_chunk(self, seeders, chunk_idx, file_parts, filename, semaphore):
        """Download a single chunk from available seeders"""
        try:
            for attempt in range(MAX_RETRIES):
                idx = attempt % len(seeders)
                ip, port = seeders[idx]
                
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(10)
                        sock.connect((ip, int(port)))
                        sock.send(f"REQUEST {filename} {chunk_idx}".encode())
                        
                        # First line should contain the hash
                        response = b""
                        hash_received = False
                        chunk_hash = None
                        
                        while True:
                            chunk = sock.recv(4096)
                            if not chunk:
                                break
                                
                            if not hash_received:
                                # Process the first line for hash
                                response += chunk
                                if b'\n' in response:
                                    header, rest = response.split(b'\n', 1)
                                    if header.startswith(b'HASH '):
                                        chunk_hash = header[5:].decode()
                                        response = rest
                                    hash_received = True
                            else:
                                response += chunk
                        
                        if response:
                            # Verify integrity if hash was provided
                            if chunk_hash:
                                calculated_hash = hashlib.sha256(response).hexdigest()
                                if calculated_hash != chunk_hash:
                                    logging.warning(f"Chunk {chunk_idx} hash mismatch, retrying...")
                                    continue
                                self.chunk_hashes[chunk_idx] = chunk_hash
                            
                            file_parts[chunk_idx] = response
                            self.downloaded_chunks += 1
                            
                            # Update progress bar
                            progress_value = self.downloaded_chunks * 100 / self.total_chunks
                            self.master.after(0, self.progress.config, {"value": progress_value})
                            self.master.after(0, self.chunk_label.config, 
                                             {"text": f"Chunks: {self.downloaded_chunks}/{self.total_chunks}"})
                            
                            return True
                except Exception as e:
                    logging.error(f"Error downloading chunk {chunk_idx}: {str(e)}")
                    continue
        finally:
            semaphore.release()
        
        logging.error(f"Failed to download chunk {chunk_idx} after {MAX_RETRIES} attempts")
        return False

    def register_as_seeder(self, filename, file_path):
        """Register as a seeder for a completed download"""
        try:
            logging.info(f"Would register as seeder for {filename} (at {file_path})")
            messagebox.showinfo("Seeder", 
                               f"Download complete! You're now a potential seeder for {filename}.\n"
                               "To actually seed, run the seeder.py script.")
        except Exception as e:
            logging.error(f"Error registering as seeder: {str(e)}")

    def reseed_files(self):
        """Show dialog for reseeding downloaded files and start seeder.py for selected files."""
        download_dir = "downloads"
        
        # Check if the downloads folder exists and contains files
        if not os.path.exists(download_dir) or not os.listdir(download_dir):
            messagebox.showinfo("Reseed", "No completed downloads to reseed.")
            return
        
        # List all files in the downloads folder
        files_str = "\n".join(os.listdir(download_dir))
        
        # Prompt the user for confirmation
        confirm = messagebox.askyesno("Reseed Files", 
                                     f"You have the following files available for reseeding:\n\n{files_str}\n\n"
                                     "Do you want to start seeding these files?")
        
        if not confirm:
            return
        
        # Prompt the user to specify a port for seeding (optional)
        port = simpledialog.askinteger("Reseed Port", 
                                       "Enter the port number for seeding (default is 6002):\n"
                                       "Leave blank to use the default port.", 
                                       minvalue=1024, maxvalue=65535)
        
        # If the user cancels the input, do not proceed
        if port is None:
            return
        
        # Construct the command to run seeder.py
        seeder_script = "seeder.py"
        
        # If a port is specified, include it in the command
        if port:
            command = f"python {seeder_script} -p {port}"
        else:
            command = f"python {seeder_script}"
        
        # Run the command in a new terminal window
        try:
            if os.name == "nt":  # Windows
                subprocess.Popen(["start", "cmd", "/k", command], shell=True)
            elif os.name == "posix":  # macOS/Linux
                subprocess.Popen(["gnome-terminal", "--", "bash", "-c", command])
            else:
                messagebox.showerror("Error", "Unsupported operating system for terminal spawning.")
                return
            
            messagebox.showinfo("Reseed", f"Seeder started. You are now seeding the downloaded files.")
        except Exception as e:
            logging.error(f"Error starting seeder: {str(e)}")
            messagebox.showerror("Error", f"Failed to start seeder: {str(e)}")

    def refresh_seeders(self):
        """Refresh the number of active seeders"""
        if self.current_file:
            seeders = self.request_seeders(self.current_file)
            self.active_seeders = len(seeders)
            self.master.after(0, self.active_seeders_label.config, {"text": str(self.active_seeders)})

if __name__ == "__main__":
    root = tk.Tk()
    app = LeecherUI(root)
    root.mainloop()