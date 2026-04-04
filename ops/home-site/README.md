# Home Policy Site

This directory contains a standalone Terraform deployment and a small Python + Nginx app for:

- `https://home.moshq.app/privacy`
- `https://home.moshq.app/terms`
- `https://home.moshq.app/data`

The app intentionally avoids framework dependencies. It serves the public policy pages and stores
submitted privacy/deletion requests in a local SQLite database on the server.
