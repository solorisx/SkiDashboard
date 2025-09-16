import json
import logging


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, '%Y-%m-%dT%H:%M:%S'),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage().replace('\n', '\\n').replace('\r', '\\r'),
            "exc_info": self.formatException(record.exc_info) if record.exc_info else None,
            "stack_info": self.formatStack(record.stack_info) if record.stack_info else None,
        }
        return json.dumps(log_data)