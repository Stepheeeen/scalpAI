import csv
import os
import time
import json
import logging
from datetime import datetime

class TickLogger:
    def __init__(self, csv_filename: str, json_filename: str = "bot_audit.log"):
        self.csv_filename = csv_filename
        self.json_filename = json_filename
        self.headers = ["timestamp", "bid", "ask", "server_time", "local_time", "latency_ms"]
        self._init_csv()
        
        # Setup audit logging
        self.audit_logger = logging.getLogger("AuditLogger")
        self.audit_logger.setLevel(logging.INFO)
        
        # Avoid duplicate handlers
        if not self.audit_logger.handlers:
            fh = logging.FileHandler(self.json_filename)
            formatter = logging.Formatter('%(message)s')
            fh.setFormatter(formatter)
            self.audit_logger.addHandler(fh)

    def _init_csv(self):
        if not os.path.exists(self.csv_filename):
            with open(self.csv_filename, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)

    def log_tick(self, bid: float, ask: float, server_time_ms: int):
        local_time_ms = int(time.time() * 1000)
        latency = local_time_ms - server_time_ms
        
        dt_object = datetime.fromtimestamp(local_time_ms / 1000.0)
        timestamp_str = dt_object.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        with open(self.csv_filename, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp_str,
                f"{bid:.5f}",
                f"{ask:.5f}",
                server_time_ms,
                local_time_ms,
                latency
            ])
        
        return latency

    def log_audit(self, event_type: str, details: dict):
        """Logs structured JSON events for production auditing."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "details": details
        }
        self.audit_logger.info(json.dumps(entry))
