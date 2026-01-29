# Security Desktop - Lightweight Debian with Security Tools
# Browser accessible via noVNC at port 3000

FROM lscr.io/linuxserver/webtop:debian-xfce

# Install essential security tools (lightweight selection)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Network Scanning & Enumeration
    nmap \
    masscan \
    netcat-openbsd \
    dnsutils \
    whois \
    traceroute \
    tcpdump \
    tshark \
    # Web Security
    nikto \
    dirb \
    sqlmap \
    # Password & Crypto
    hydra \
    john \
    hashcat \
    sslscan \
    # Utilities
    curl \
    wget \
    git \
    vim \
    nano \
    tmux \
    htop \
    net-tools \
    iputils-ping \
    openssh-client \
    proxychains4 \
    tor \
    # Python for scripting
    python3 \
    python3-pip \
    python3-venv \
    # Build essentials for compiling tools
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Go for modern security tools
RUN apt-get update && apt-get install -y --no-install-recommends golang-go \
    && rm -rf /var/lib/apt/lists/*

ENV GOPATH=/root/go
ENV PATH="${GOPATH}/bin:/usr/local/go/bin:${PATH}"

# Install modern security tools via Go
RUN go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest && \
    go install github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest && \
    go install github.com/ffuf/ffuf/v2@latest && \
    go install github.com/tomnomnom/waybackurls@latest && \
    go install github.com/tomnomnom/httprobe@latest && \
    go install github.com/OJ/gobuster/v3@latest

# Install Python security tools
RUN pip3 install --no-cache-dir --break-system-packages \
    requests \
    beautifulsoup4 \
    pwntools \
    impacket \
    scapy \
    paramiko \
    python-nmap

# Create tools directory
RUN mkdir -p /opt/tools

# Download useful wordlists
RUN mkdir -p /usr/share/wordlists && \
    wget -q -O /usr/share/wordlists/rockyou.txt.gz \
    https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt.gz && \
    gunzip /usr/share/wordlists/rockyou.txt.gz || true

# Clone SecLists (common wordlists for security testing)
RUN git clone --depth 1 https://github.com/danielmiessler/SecLists.git /usr/share/seclists

# Create optional Metasploit install script (run manually if needed)
RUN echo '#!/bin/bash\n\
echo "Installing Metasploit Framework..."\n\
curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > /tmp/msfinstall\n\
chmod 755 /tmp/msfinstall\n\
/tmp/msfinstall\n\
echo "Metasploit installed! Run msfconsole to start."' > /usr/local/bin/install-metasploit.sh && \
    chmod +x /usr/local/bin/install-metasploit.sh

# Create desktop shortcuts for common tools
RUN mkdir -p /config/Desktop && \
    echo '[Desktop Entry]\n\
Type=Application\n\
Name=Terminal\n\
Exec=xfce4-terminal\n\
Icon=utilities-terminal\n\
Terminal=false\n\
Categories=System;' > /config/Desktop/terminal.desktop && \
    chmod +x /config/Desktop/terminal.desktop

# Set environment for security tools
ENV TERM=xterm-256color

# Expose web VNC port
EXPOSE 3000

# Volume for persistent data
VOLUME /config
