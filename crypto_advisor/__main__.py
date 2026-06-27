import argparse

from .server import serve


def main():
    parser = argparse.ArgumentParser(description="Crypto Advisor — local paper-trading dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default 8000)")
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
