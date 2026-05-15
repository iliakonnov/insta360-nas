# Insta360 NAS Server

This project simulates an Insta360 camera, allowing the official Insta360 app to connect to a hosted server (e.g., your NAS) and read files directly from it, instead of requiring a real physical camera with an SD card.

## Features

- **App Simulation**: Implements the camera's RTMP and HTTP protocols so the official Insta360 app can connect seamlessly.
- **Virtual Directory Merging**: Dynamically searches for `Camera01` subdirectories across multiple top-level directories on your NAS. It merges and presents them as a single, unified `/DCIM/` folder to the app.
- **HTTP Admin & Dashboard**: Includes a built-in web dashboard where you can manage user access, authorize users, and undelete/unhide files.
- **File Management & Tracking**: Maintains an SQLite database to track authorized users, directory access, and safely handles file deletion requests by "hiding" them instead of deleting your actual media.

## Network Requirements

For the official Insta360 app to successfully connect to your server, your network configuration must meet these strict requirements:

- **Wi-Fi SSID**: Your network must broadcast a specific SSID format, such as `X5 [Name].OSC` (e.g., `X5 EXAMP.OSC`).
- **IP Address**: The server must be accessible at `192.168.42.1`. The app expects the camera to be running at this exact IP address.

You will need to configure your network or NAS to act as an access point broadcasting this SSID and routing the IP address appropriately.

## Configuration

Camera details and application secrets are managed via a standalone JSON configuration file. You can find a template in `example-config.json`.

```json
{
  "device_name": "Insta360 Example",
  "camera_type": "Insta360 X5",
  "firmware_revision": "v1.13.3",
  "serial_number": "EXAMP123456789",
  "ota_pkg_version": "v1.13.3",
  "wifi_ssid": "X5 EXAMP.OSC",
  "wifi_password": "ExamplePassword123"
}
```

Make sure the `wifi_ssid` and `wifi_password` match the actual access point you configured for the app to connect to.

## Installation & Usage

You can run the server directly using Python or via NixOS.

### Option 1: Running with Python

To run the server locally, you will first need to initialize the git submodules and install the required dependencies.

1. **Initialize Submodules**:
   ```bash
   git submodule update --init --recursive
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r insta360-server/requirements.txt
   ```

3. **Run the Server**:
   ```bash
   python insta360-server/server.py \
     --dir /path/to/your/media \
     --config-file example-config.json \
     --bind 192.168.42.1
   ```

### Option 2: Running with NixOS

The repository includes a Nix flake and exposes a NixOS module (`services.insta360-nas`) for declarative configuration.

Include the project as an input in your `flake.nix`, and configure the service in your system configuration:

```nix
{
  services.insta360-nas = {
    enable = true;
    bind = "192.168.42.1";
    dir = "/data/@storage/Photos"; # Directory to serve files from
    configFile = "/var/lib/insta360-nas/config.json"; # Path to your configuration JSON
  };
}
```

By default, the NixOS service will run both the HTTP and RTSP servers, persisting the database to the state directory (`/var/lib/insta360-nas/`).
