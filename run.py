#!/usr/bin/env python3
"""PWA proxy launcher — serves static PWA files + proxies to Streamlit."""
import asyncio
import os
import subprocess
import sys
import time

PROXY_PORT = int(os.environ.get("PORT", 8500))
STREAMLIT_PORT = 8501
PWA_DIR = os.path.join(os.path.dirname(__file__), "backend", "pwa")
APP_PATH = os.path.join(os.path.dirname(__file__), "backend", "app.py")

STATIC_MAP = {
    "/manifest.json": ("application/json", "manifest.json"),
    "/sw.js": ("application/javascript", "sw.js"),
    "/icon-192.png": ("image/png", "icon-192.png"),
    "/icon-512.png": ("image/png", "icon-512.png"),
    "/favicon.ico": ("image/x-icon", "icon-512.png"),
}


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def serve_static(path):
    if path not in STATIC_MAP:
        return None, None, None
    content_type, filename = STATIC_MAP[path]
    filepath = os.path.join(PWA_DIR, filename)
    if not os.path.exists(filepath):
        return None, None, None
    with open(filepath, "rb") as f:
        data = f.read()
    return content_type, data, filepath


async def handle(reader, writer):
    try:
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = await reader.read(4096)
            if not chunk:
                writer.close()
                return
            buf += chunk

        idx = buf.find(b"\r\n\r\n") + 4
        header_data = buf[:idx]
        extra = buf[idx:]

        first_line = header_data.split(b"\r\n")[0].decode("utf-8", errors="replace")
        parts = first_line.split(" ")
        path = parts[1] if len(parts) > 1 else "/"

        ct, data, _ = serve_static(path)
        if data is not None:
            resp = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: {ct}\r\n"
                f"Content-Length: {len(data)}\r\n"
                f"Cache-Control: public, max-age=3600\r\n"
                f"\r\n"
            ).encode() + data
            writer.write(resp)
            await writer.drain()
            writer.close()
            return

        s_reader, s_writer = await asyncio.open_connection("127.0.0.1", STREAMLIT_PORT)
        s_writer.write(header_data + extra)
        await s_writer.drain()

        await asyncio.gather(
            pipe(reader, s_writer),
            pipe(s_reader, writer),
        )
    except (ConnectionRefusedError, OSError):
        try:
            writer.write(
                b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n"
                b"Content-Length: 22\r\n\r\nStreamlit not running."
            )
            await writer.drain()
        except Exception:
            pass
        writer.close()
    except Exception:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "streamlit", "run", APP_PATH,
        "--server.port", str(STREAMLIT_PORT),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    await asyncio.sleep(3)

    server = await asyncio.start_server(handle, "0.0.0.0", PROXY_PORT)
    addr = server.sockets[0].getsockname()
    print(f"  Stock Analyzer: http://localhost:{addr[1]}")
    print(f"  📱 Add to Home Screen for PWA mode")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
