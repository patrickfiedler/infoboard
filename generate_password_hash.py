#!/usr/bin/env python3
"""
Utility script to generate bcrypt password hash for config.json
"""
import bcrypt
import getpass


def generate_hash():
    """Generate a bcrypt hash for a password."""
    print("Kundenstopper Password Hash Generator")
    print("=" * 40)

    password = getpass.getpass("Enter password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        print("\nError: Passwords do not match!")
        return

    # Generate hash
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    hash_string = password_hash.decode('utf-8')

    print("\n" + "=" * 40)
    print("Password hash generated successfully!")
    print("=" * 40)
    print("\nAdd this to your config.json file:")
    print(f'\n"admin_password_hash": "{hash_string}"')
    print("\n" + "=" * 40)


if __name__ == '__main__':
    generate_hash()
