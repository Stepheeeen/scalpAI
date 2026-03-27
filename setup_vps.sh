#!/bin/bash

# XAU/USD HFT Bot - VPS Setup Script (Ubuntu)
# Target: Equinix NY4 VPS

echo "--- 🚀 HFT Bot Setup Starting ---"

# 1. Update System
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-dev git curl

# 2. Install Project Dependencies
pip3 install websockets protobuf python-dotenv pyyaml python-telegram-bot grpcio-tools pandas numpy xgboost scikit-learn

# 3. Optimize Network for Low Latency
echo "--- ⚡ Optimizing Network Stack ---"
cat <<EOF | sudo tee -a /etc/sysctl.conf
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_low_latency = 1
net.ipv4.tcp_slow_start_after_idle = 0
EOF
sudo sysctl -p

# 4. Setup Systemd Service
echo "--- ⚙️ Installing Systemd Service ---"
PROJECT_DIR=$(pwd)
sed -i "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|g" bot.service
sed -i "s|ExecStart=.*|ExecStart=$(which python3) main.py|g" bot.service
sudo cp bot.service /etc/systemd/system/hftbot.service
sudo systemctl daemon-reload
sudo systemctl enable hftbot.service

echo "--- ✅ Setup Complete ---"
echo "Instructions:"
echo "1. Edit your .env file with your credentials."
echo "2. Run 'sudo systemctl start hftbot.service' to start the bot."
echo "3. Use 'journalctl -u hftbot.service -f' to monitor logs."
