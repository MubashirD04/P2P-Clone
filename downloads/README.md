# P2P BitTorrent Clone

A peer-to-peer file sharing system that implements core BitTorrent functionality using Python. This project includes a central tracker, multiple seeders, and leechers for distributed file sharing.

## Overview

This BitTorrent Clone consists of three main components:

- **Tracker** - Central server that maintains a registry of seeders and handles peer discovery
- **Seeder** - Distributes files to leechers in 512 KB chunks with SHA-256 verification
- **Leecher** - Downloads files from seeders with a user-friendly GUI interface

## Features

- **Distributed Architecture**: Tracker-based peer discovery for scalability
- **Chunk-Based Transfer**: Files are transferred in 512 KB chunks for efficient streaming
- **Data Integrity**: SHA-256 hashing for every chunk to verify data authenticity
- **Concurrent Transfers**: Multi-threaded design supporting simultaneous uploads and downloads
- **GUI Interface**: User-friendly Tkinter interface for leechers to check availability and download files
- **Reseeding**: Leechers can reseed downloaded files to other peers
- **Logging**: Detailed activity logs for tracking all operations
- **Graceful Shutdown**: Coordinated shutdown mechanism between tracker and seeders

## System Requirements

- Python 3.7+
- No external dependencies (uses standard library)
- Cross-platform support (Windows, macOS, Linux)

## Installation

```bash
# Clone or download the repository
cd BitTorrent_Clone

# No additional packages required
# Uses only Python standard library
```

## Usage

### 1. Start the Tracker

Start the tracker server first (it must be running before seeders and leechers connect):

```bash
python tracker.py
```

The tracker will:
- Listen on `localhost:5000` (UDP)
- Maintain a registry of available files and their seeders
- Handle peer discovery requests

### 2. Start Seeders

Open a new terminal and start one or more seeders:

```bash
python seeder.py
```

The seeder will:
- Connect to the tracker on `localhost:5000`
- Scan the local directory for files to seed
- Register files with the tracker
- Hash all file chunks for integrity verification
- Listen for download requests on `localhost:6002` (TCP)
- Display upload progress as files are requested

### 3. Start Leechers

Open another terminal and start the leecher GUI:

```bash
python leecher.py
```

The leecher interface provides:
- **Check Availability**: Search for available files on the network
- **Download**: Download selected files from available seeders
- **Reseed Files**: Automatically reseed previously downloaded files
- Real-time download progress tracking
- Download history and status display

## Architecture Details

### Configuration Parameters

All components use the following default settings:

- **Tracker Address**: `localhost:5000` (UDP)
- **Seeder Default Port**: `6002` (TCP)
- **Chunk Size**: 512 KB
- **Max Connection Retries**: 5
- **Hash Algorithm**: SHA-256

### Data Flow

1. **Seeder Registration**
   - Seeder calculates hashes for all file chunks
   - Registers files with tracker via UDP message
   - Listens for incoming download requests

2. **Peer Discovery**
   - Leecher queries tracker for available seeders
   - Tracker returns list of seeders for requested file
   - Leecher selects seeder and initiates TCP connection

3. **File Download**
   - Leecher downloads file in sequential chunks
   - Each chunk is verified against the seeder's hash
   - Progress is displayed in real-time

4. **Reseeding**
   - Completed files can be reseed by the leecher
   - Leecher registers with tracker for downloaded files
   - Acts as both seeder and leecher

## Logging

Each component generates detailed logs:

- **tracker_logs.txt**: Tracker operations and peer registrations
- **seeder_logs.txt**: File registrations, uploads, and system events
- **leecher_logs.txt**: Download attempts, completions, and errors

Logs include timestamps and severity levels (INFO, ERROR, etc.).

## Project Structure

```
BitTorrent_Clone/
├── tracker.py          # Tracker server implementation
├── seeder.py           # Seeder implementation
├── leecher.py          # Leecher GUI implementation
└── README.md           # This file
```

## Technical Implementation

### Core Components

- **Socket Programming**: UDP for tracker communication, TCP for file transfers
- **Threading**: Multi-threaded servers for handling concurrent connections
- **Hash Verification**: SHA-256 for chunk integrity validation
- **GUI Framework**: Tkinter for cross-platform interface
- **Progress Tracking**: Real-time progress bars for uploads/downloads

## Limitations and Notes

- Local network communication (currently configured for localhost)
- Single tracker instance (no high availability)
- Files must be in seeder's working directory
- No encryption for data transmission
- No bandwidth throttling

## License

This project is provided as-is for educational purposes.

## Author

Created as an implementation of peer-to-peer file sharing systems.
