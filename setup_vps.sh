#!/bin/bash

# XAU/USD HFT Bot - Equinix NY4 High-Performance Setup
echo "--- 🚀 Equinix HFT Bot Deployment Starting ---"

# 1. System Update & Dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-dev python3-venv git curl chrony ufw

# 2. High-Precision Clock Sync (Critical for NY4/HFT)
echo "--- 🕒 Configuring High-Precision Clock Sync ---"
sudo systemctl enable chrony
sudo systemctl start chrony
# Force immediate sync
sudo chronyc -a makestep

# 3. Network Stack Optimization (Low Latency Tuning)
echo "--- ⚡ Optimizing Network Stack for NY4 ---"
cat <<EOF | sudo tee /etc/sysctl.d/99-hft-optimizations.conf
# Increase max open files
fs.file-max = 100000

# TCP Latency Optimizations
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_low_latency = 1
net.ipv4.tcp_slow_start_after_idle = 0
net.ipv4.tcp_fastopen = 3
net.core.busy_poll = 50
net.core.busy_read = 50
net.ipv4.tcp_nodelay = 1
EOF
sudo sysctl -p /etc/sysctl.d/99-hft-optimizations.conf

# 4. Firewall Hardening
echo "--- 🛡️ Configuring Firewall ---"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw --force enable

# 5. Project Dependencies
echo "--- 📦 Installing Python Dependencies in Virtual Environment ---"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install websockets protobuf python-dotenv pyyaml python-telegram-bot grpcio-tools pandas numpy xgboost scikit-learn

# 6. Ensure directories are treated as packages
touch openapi_pb2/__init__.py
touch protos/__init__.py

# 7. Service Installation
echo "--- ⚙️ Configuring Systemd Service ---"
PROJECT_DIR=$(pwd)
PYTHON_PATH="$PROJECT_DIR/venv/bin/python3"

# Update placeholders in service file
sed -i "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" bot.service
sed -i "s|{{PYTHON_PATH}}|$PYTHON_PATH|g" bot.service

sudo cp bot.service /etc/systemd/system/hftbot.service
sudo systemctl daemon-reload
sudo systemctl enable hftbot.service

echo "--- ✅ Equinix Setup Complete ---"
echo "Next Steps:"
echo "1. Create your .env file: nano .env"
echo "2. Start the bot: sudo systemctl start hftbot.service"
echo "3. Monitor performance: journalctl -u hftbot.service -f"
