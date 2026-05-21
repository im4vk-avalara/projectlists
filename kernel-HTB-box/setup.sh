#!/bin/bash
# HTB box setup — runs inside the VM as the dev user (has passwordless sudo)
set -e

echo "[*] === HTB Box Setup ==="

# ------------------------------------------------------------------ #
# 1. Install vulndev.ko to a system location                          #
# ------------------------------------------------------------------ #
echo "[*] Installing vulndev.ko..."

sudo mkdir -p /opt/vulndev
sudo cp ~/vulndev.ko /opt/vulndev/vulndev.ko
sudo chmod 644 /opt/vulndev/vulndev.ko

echo "[+] Module installed at /opt/vulndev/vulndev.ko"

# ------------------------------------------------------------------ #
# 2. Create systemd service to load module at boot                    #
# ------------------------------------------------------------------ #
echo "[*] Creating systemd service..."

sudo tee /etc/systemd/system/vulndev.service > /dev/null <<'EOF'
[Unit]
Description=VulnDev Kernel Module
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/sbin/insmod /opt/vulndev/vulndev.ko
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable vulndev.service
echo "[+] vulndev.service enabled"

# ------------------------------------------------------------------ #
# 3. Create player user (HTB foothold)                                #
# ------------------------------------------------------------------ #
echo "[*] Creating player user..."

sudo useradd -m -s /bin/bash player
echo "player:player123" | sudo chpasswd
echo "[+] player user created (password: player123)"

# ------------------------------------------------------------------ #
# 4. Drop flags                                                        #
# ------------------------------------------------------------------ #
echo "[*] Dropping flags..."

# user flag — readable by player
USER_FLAG="HTB{k3rn3l_pwn_st4rts_w1th_4_s1ngl3_0v3rfl0w}"
echo "$USER_FLAG" | sudo tee /home/player/user.txt > /dev/null
sudo chown player:player /home/player/user.txt
sudo chmod 644 /home/player/user.txt

# root flag — readable only by root
ROOT_FLAG="HTB{c0mm1t_cr3ds_g1v3s_y0u_th3_k3rn3l}"
echo "$ROOT_FLAG" | sudo tee /root/root.txt > /dev/null
sudo chown root:root /root/root.txt
sudo chmod 600 /root/root.txt

echo "[+] user.txt → /home/player/user.txt"
echo "[+] root.txt → /root/root.txt"

# ------------------------------------------------------------------ #
# 5. Copy vulndev.ko to player home so they can reverse it            #
# ------------------------------------------------------------------ #
sudo cp /opt/vulndev/vulndev.ko /home/player/vulndev.ko
sudo chown player:player /home/player/vulndev.ko
sudo chmod 644 /home/player/vulndev.ko
echo "[+] vulndev.ko placed in /home/player/ for reversing"

# ------------------------------------------------------------------ #
# 6. Harden: remove dev user's sudo and lock it down                  #
# ------------------------------------------------------------------ #
echo "[*] Locking down dev user..."
# Comment this out during development — uncomment before final export
# sudo deluser dev sudo
# sudo passwd -l dev

echo ""
echo "[+] === Setup Complete ==="
echo ""
echo "    SSH access : ssh player@<ip>  (password: player123)"
echo "    Device     : /dev/vulndev     (permissions: 0666)"
echo "    Module src : /home/player/vulndev.ko"
echo "    User flag  : /home/player/user.txt"
echo "    Root flag  : /root/root.txt (root only)"
