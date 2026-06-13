try:
    from app import app
except Exception as e:
    import traceback
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def crash_handler(path):
        return f"<h1>Startup Crash Traceback</h1><pre>{traceback.format_exc()}</pre>", 500
