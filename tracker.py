import socket
import threading
import time
import logging
import os

# Configure logging
logging.basicConfig(
    filename="tracker_logs.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Dictionary to store seeders: {filename: [(seeder_ip, seeder_port, timestamp)]}
seeder_list = {}

# Tracker settings
TRACKER_IP = "localhost"  # Localhost for testing
TRACKER_PORT = 5000  # UDP port

def handle_requests():
    # Handles incoming UDP messages from seeders and leechers
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tracker_socket:
        tracker_socket.bind((TRACKER_IP, TRACKER_PORT))

        logging.info(f"Tracker started at {TRACKER_IP}:{TRACKER_PORT}")
        print(f"Tracker is running on {TRACKER_IP}:{TRACKER_PORT}")
        print("Waiting for seeders and leechers to connect...")

        while True:
            try:
                data, addr = tracker_socket.recvfrom(1024)
                message = data.decode().strip().split()

                # Handle SHUTDOWN command from leecher
                if message and message[0] == "SHUTDOWN":
                    logging.info("Received shutdown request")
                    print("Shutdown request received. Notifying seeders...")

                    for filename, seeders in seeder_list.items():
                        for seeder in seeders:
                            seeder_ip, seeder_port, _ = seeder
                            try:
                                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                                    sock.sendto(b"SHUTDOWN", (seeder_ip, seeder_port))
                                    logging.info(f"Notified seeder {seeder_ip}:{seeder_port}")
                            except Exception as e:
                                logging.error(f"Error notifying seeder: {e}")

                    print("Tracker shutting down...")
                    os._exit(0)

                if message[0] == "REGISTER":
                    if len(message) != 3:
                        logging.error(f"Invalid REGISTER format from {addr}: {data.decode()}")
                        tracker_socket.sendto(b"ERROR: Invalid REGISTER format", addr)
                        continue

                    filename, seeder_port = message[1], int(message[2])

                    logging.info(f"Processing registration for {filename} from {addr}")

                    # Add seeder to the list, avoid duplicates
                    if filename not in seeder_list:
                        seeder_list[filename] = []

                    existing_seeders = [(ip, port) for ip, port, _ in seeder_list[filename]]
                    if (addr[0], seeder_port) not in existing_seeders:
                        seeder_list[filename].append((addr[0], seeder_port, time.time()))
                        logging.info(f"Seeder {addr[0]}:{seeder_port} registered file: {filename}")
                    else:
                        for i, (ip, port, _) in enumerate(seeder_list[filename]):
                            if ip == addr[0] and port == seeder_port:
                                seeder_list[filename][i] = (ip, port, time.time())
                        logging.info(f"Seeder {addr[0]}:{seeder_port} already registered for file: {filename}")

                    # Send confirmation response
                    response_message = f"REGISTERED {filename}"
                    tracker_socket.sendto(response_message.encode(), addr)
                    logging.info(f"Sent response to seeder at {addr}: {response_message}")

                elif message[0] == "REQUEST":
                    if len(message) != 2:
                        logging.error(f"Invalid REQUEST format from {addr}: {data.decode()}")
                        tracker_socket.sendto(b"ERROR: Invalid REQUEST format", addr)
                        continue

                    filename = message[1]

                    # Find active seeders for the file
                    if filename in seeder_list:
                        active_seeders = [(ip, port) for ip, port, timestamp in seeder_list[filename] if time.time() - timestamp < 30]

                        if active_seeders:
                            response = "SEEDERS " + " ".join([f"{ip}:{port}" for ip, port in active_seeders])
                            logging.info(f"Sent active seeder list for {filename}: {response}")
                        else:
                            response = "NO_SEEDERS"
                            logging.warning(f"No active seeders available for {filename}.")
                    else:
                        response = "NO_SEEDERS"
                        logging.warning(f"No seeders found for {filename}.")

                    tracker_socket.sendto(response.encode(), addr)

                elif message[0] == "HEARTBEAT":
                    if len(message) != 2:
                        logging.error(f"Invalid HEARTBEAT format from {addr}: {data.decode()}")
                        tracker_socket.sendto(b"ERROR: Invalid HEARTBEAT format", addr)
                        continue

                    filename = message[1]

                    if filename in seeder_list:
                        updated = False
                        for i, (ip, port, _) in enumerate(seeder_list[filename]):
                            if ip == addr[0]:
                                seeder_list[filename][i] = (ip, port, time.time())
                                updated = True
                                logging.info(f"Heartbeat received from {addr[0]} for {filename}")
                        
                        if not updated:
                            logging.warning(f"Heartbeat received from non-registered seeder {addr[0]} for {filename}")
                    else:
                        logging.warning(f"Heartbeat received for non-registered file {filename} from {addr[0]}")

            except Exception as e:
                logging.error(f"Unexpected error: {e}")

# Function to remove inactive seeders
def remove_inactive_seeders():
    while True:
        time.sleep(10)
        for filename, seeders in seeder_list.items():
            active_seeders = [(ip, port, timestamp) for ip, port, timestamp in seeders if time.time() - timestamp < 60]

            if len(active_seeders) != len(seeders):
                logging.warning(f"Removed inactive seeders for {filename}. Active seeders: {len(active_seeders)}")

            if active_seeders:
                seeder_list[filename] = active_seeders
            else:
                del seeder_list[filename]

if __name__ == "__main__":
    threading.Thread(target=handle_requests, daemon=True).start()
    threading.Thread(target=remove_inactive_seeders, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Tracker shutting down...")