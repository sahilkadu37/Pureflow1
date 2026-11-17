from app import create_app
import os

app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("PUREFLOW_HOST", os.environ.get("AQUAINTEL_HOST", "127.0.0.1")),
        port=int(os.environ.get("PUREFLOW_PORT", os.environ.get("AQUAINTEL_PORT", "5000"))),
        debug=app.config["DEBUG"],
    )
