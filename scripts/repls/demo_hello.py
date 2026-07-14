"""Demo script - Hello World capability."""

def main(payload):
    """Main entry point for the script."""
    name = payload.get("name", "World")
    message = f"Hello, {name}!"
    
    # Use print to show output
    print(f"🤖 Script says: {message}")
    
    return {
        "message": message,
        "timestamp": __import__('time').time(),
        "status": "success"
    }


if __name__ == "__main__":
    # Direct execution test
    result = main({"name": "AOS"})
    print("Direct test:", result)