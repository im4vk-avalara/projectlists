# Security Desktop

A lightweight Debian-based security testing environment accessible via browser.

## Quick Start

```bash
# Build and start
docker compose up -d --build

# Access via browser
open http://localhost:3000
```

## Included Tools

### Network Scanning & Enumeration
- **nmap** - Network mapper and port scanner
- **masscan** - Fast TCP port scanner
- **netcat** - Network utility (nc)
- **tcpdump** - Packet analyzer
- **tshark** - Terminal Wireshark

### Web Security
- **nikto** - Web server scanner
- **dirb** - Web content scanner
- **gobuster** - Directory/DNS busting
- **ffuf** - Fast web fuzzer
- **sqlmap** - SQL injection tool
- **nuclei** - Vulnerability scanner
- **httpx** - HTTP toolkit

### Reconnaissance
- **subfinder** - Subdomain discovery
- **waybackurls** - Fetch URLs from Wayback Machine
- **httprobe** - Probe for working HTTP servers
- **whois/dig** - DNS utilities

### Password & Crypto
- **hydra** - Password cracker
- **john** - John the Ripper
- **hashcat** - Advanced password recovery
- **sslscan** - SSL/TLS scanner

### Exploitation
- **metasploit-framework** - Exploitation framework
- **impacket** - Python network protocols
- **pwntools** - CTF/exploit development

### Utilities
- **proxychains4** - Proxy chains
- **tor** - Anonymity network
- **tmux** - Terminal multiplexer
- **git, curl, wget, vim, nano**

### Wordlists
- `/usr/share/wordlists/rockyou.txt` - Common passwords
- `/usr/share/seclists/` - SecLists collection

## Ports

| Port | Service |
|------|---------|
| 3000 | Web Desktop (noVNC) |

## Usage Tips

```bash
# Stop the container
docker compose down

# View logs
docker compose logs -f

# Shell into container
docker exec -it security-desktop bash

# Rebuild after Dockerfile changes
docker compose up -d --build --force-recreate
```

## Network Scanning (Host Network Mode)

To scan your local network, uncomment `network_mode: host` in docker-compose.yml:

```yaml
network_mode: host
```

Note: This disables port mapping; access via `http://localhost:3000`
