import json
import os

CONFIG_FILE = 'config.json'


class Config:
    """Configuration management for the application."""

    def __init__(self):
        self.config = self._load_config()

    def _load_config(self):
        """Load configuration from JSON file."""
        if not os.path.exists(CONFIG_FILE):
            raise FileNotFoundError(
                f"{CONFIG_FILE} not found. Please create it from config.json.example"
            )

        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)

    def get(self, key, default=None):
        """Get a configuration value."""
        return self.config.get(key, default)

    @property
    def admin_username(self):
        """Get admin username."""
        return self.config.get('admin_username', 'admin')

    @property
    def admin_password_hash(self):
        """Get admin password hash."""
        return self.config.get('admin_password_hash', '')

    @property
    def secret_key(self):
        """Get Flask secret key."""
        return self.config.get('secret_key', 'change-me-in-production')

    @property
    def port(self):
        """Get server port."""
        return self.config.get('port', 8080)

    @property
    def host(self):
        """Get server host."""
        return self.config.get('host', '0.0.0.0')

    @property
    def upload_folder(self):
        """Get upload folder path."""
        return self.config.get('upload_folder', 'uploads')


# Global config instance
config = Config()
