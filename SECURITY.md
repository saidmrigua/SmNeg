# Security policy

SMneg is a desktop application that works on local files. It makes no network connections, has no accounts
and stores no credentials.

## Reporting a vulnerability
Please **do not open a public issue** for a security problem (for example a crafted RAW/TIFF file that makes the app
execute code, or a flaw in a release file). Use GitHub's private reporting instead:
**Security tab → [Report a vulnerability](https://github.com/saidmrigua/SmNeg/security/advisories/new)**.

Include the version, your operating system, the steps to reproduce and, if possible, a sample file.
You will get an answer as soon as possible; this is a one-person project, so please allow a few days.

## Supported versions
Only the latest release receives fixes.

## Scope notes
- Image decoding is done by LibRaw, Pillow and OpenCV. Problems inside those libraries should also be reported to
  their projects; keep your installed versions up to date.
- The release apps are not code-signed. Always download them from the
  [official Releases page](https://github.com/saidmrigua/SmNeg/releases).
