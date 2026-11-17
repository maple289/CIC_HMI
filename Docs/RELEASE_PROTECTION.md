# PREVEX HMI release builds, integrity and Windows signing

## Build choices

The standard executable filename is **CIC-HMI.exe** for development and protected
builds. One-folder builds use the **CIC-HMI/** distribution folder. This filename
does not change the PREVEX HMI product identity or existing operator-data location.

Development source remains readable in Git. There is no licensing server, activation,
machine binding, expiration, telemetry or Internet request in these features.
Normal monitoring/recording remains offline. Never test builds with a real command.

Use the existing project `.venv` (Python 3.12 x64); do not install system tools:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
# Optional protected-build and manifest-signature tooling:
.venv/Scripts/python.exe -m pip install -r requirements-release.txt

# Existing fast, unsigned one-folder development build:
.venv/Scripts/python.exe -m PyInstaller --noconfirm build_windows.spec

# Protected portable EXE (default), or use --layout onedir:
.venv/Scripts/python.exe scripts/build_release.py --kind protected --layout onefile --output dist/production-release
.venv/Scripts/python.exe scripts/build_release.py --kind protected --layout onedir --output dist/protected-onedir

# Development one-file is also supported:
.venv/Scripts/python.exe scripts/build_release.py --kind development --layout onefile --output dist/development-onefile
```

The helper uses Nuitka 4.3.5 package mode to compile the complete `prevex_hmi`
package into one native `.pyd`; Python application modules are excluded from the
protected PyInstaller PYZ archive. Third-party Python dependencies remain packaged
normally. Native compilation removes application docstrings. Generated C, stubs,
reports and source copies stay under `build/`, never in the distributed artifact.
The working PyInstaller development path is retained, not replaced. Optional Qt
editor stubs, tests, development scripts, internal notes and project documentation
are excluded from protected output. Required third-party licenses/font metadata
remain included. `scripts/audit_release.py` checks this distinction.

Nuitka's portable MinGW compiler is downloaded/cached **only in `.venv/nuitka-cache`**;
no system compiler is installed. First-time build tools may need Internet access.
With an already installed MSVC compiler, use `--compiler msvc`. Compilation uses
four jobs by default (`--jobs N` adjusts this). Compiler/update access is build-time
only; Nuitka update checking is disabled. Build reports are outside the artifact.
If evaluating a new Python/Qt/compiler version, repeat the tests before release.

## Hardware-only operator release (2026-11-16)

Normal startup is disconnected and hardware-only. The operator UI has no simulation
source selector, simulator generation/FID-scale fields, fault/reading/STATUS injection
controls or associated GUI handlers. Auto Detect/LEL/BTU/FID remain available. Diagnostics
keeps its summary/export controls, then the read-only **Inspect register** row, then
an expanding Modbus traffic table. Removing the FC03 suffix changes only the label;
the implementation remains FC03 on the existing serialized worker.

`load_settings()` now defaults to hardware preferences and migrates a valid legacy
simulation configuration by changing only its source mode (plus existing profile-label
normalization). Port/baud/address/timing/IDs/unit/display/recording preferences survive.
No connection, command or measurement is started by loading preferences. Historical
`simulation.sqlite3` recordings remain accessible with their original provenance;
showing those old records is not a runtime simulation option.

Protected staging bakes `runtime_policy.PRODUCTION=True` into the freshly compiled
package. Both the worker's explicit test-transport opt-in and the simulator constructor
reject simulation in this flavor. The protected CLI does not accept `--smoke-test` or
the old development COM4 bench launch options. There is no environment/configuration
switch to enable them. Shared simulator type definitions are retained where existing
strict physical-write guards reference them; those guards were not relaxed to remove
an internal type. No production simulator can be constructed or selected.

The source/development build retains an explicit isolated test harness:

```powershell
.venv/Scripts/python.exe scripts/run_hmi.py --smoke-test --data-dir tmp/development-simulation
```

Development tests use `tests/dev_support.py`, `load_settings(..., allow_simulation=True)`
and explicit `simulation_authorized=True` constructors. None of that test harness is
included in the release. Production tests use the actual unwrapped operator classes.
The simulator remains usable for source tests of all four series and command safety;
no real commands are issued. The protected release instead supports this **disconnected**
startup check (it never opens a serial port):

```powershell
./dist/production-release/CIC-HMI.exe --production-smoke-test --data-dir tmp/production-startup
```

That check verifies hardware-only/disconnected startup and the absence of simulator
widgets. It does not substitute for real-analyzer acceptance. `--verify-installation`
remains an offline resource check. Both operate with the bundled internal manifest;
the external `release-manifest.json` is never a runtime dependency. Rebuild native code
and both manifests after application changes; never reuse an older compiled application.

## Branding, attribution and the Service table

Assets are in `src/prevex_hmi/assets/`: vector SVG, preview PNG and seven-resolution
ICO (16/24/32/48/64/128/256). `scripts/prepare_icon.py` regenerates them deterministically.
The ICO is embedded in the PE resources and bundled inside both layouts for Qt;
there is no external icon requirement. The application/window icon and Windows
AppUserModelID are set at startup. Windows shortcuts should use the EXE's default
icon (or IconLocation `path-to-exe,0`), not a separate ICO. Windows Explorer can
cache old icons for a reused path; test a fresh release path when validating.

About PREVEX HMI opens from Help or Ctrl+Alt+Shift+A, in either theme. Its read-only
content is decoded from a compressed Base85 payload and checked against SHA-256.
The readable attribution source is deliberately confined to the development-only
`scripts/prepare_attribution.py`; it is not bundled. Regenerate the encoded module
with that script after an authorized attribution/version update. Encoding is
obfuscation, **not encryption**. Native compilation prevents a simple plaintext
replacement in a distributed Python file. There is no attribution editor, JSON
setting or database field. A genuine code-signing certificate's public subject may
naturally identify the signer; that is distinct from the encoded About text.

Profile Settings has seven visible columns. Restrictions/reference data remains
in profile definitions, validation, permissions and Parameter/Documented access
cell tooltips. Read Selected Setting remains FC03 on the serialized polling owner.

## Integrity checks and safe failure

Protected staging changes the integrity module's development flag before native
compilation. Operators cannot disable it with a setting or environment variable.
A bundled manifest covers the native application and supplied branding/font files.
Required native/icon/font entries must exist. Startup verifies paths and SHA-256
hashes, plus attribution, **before creating the main window, opening any SQLite
store, or starting a serial worker**. `--verify-installation` performs the same
checks and exits without data/database/serial activity. Missing, altered or invalid
components return exit code3 and show an appropriate normal-launch error. Automated
checks print an error without an unhandled-exception popup. No deletion, quarantine,
operator-data rewrite, failover command or Modbus retry is performed.

Changing attribution after startup is detected when About is opened, reported and
logged; existing monitoring continues. The startup resource check is not continuous
memory attestation. SQLite databases/settings/recordings are **not** integrity
resources. They remain in the existing AppData directory, independently of the
installation/one-file extraction directory, and must not be included in a release.
Back them up using the existing database manager before normal software updates.

An **unsigned** resource manifest detects accidental corruption and casual edits;
it does not prove who published a release. An attacker who replaces a manifest
and checker can bypass local verification. SHA-256 stored with the same program
is not proof of authenticity. Native code can also be patched or reverse engineered
by a determined person controlling the computer. There is no claim of absolute
protection. A one-folder EXE's Authenticode signature alone does not authenticate
its loose DLLs/PYD; verify the complete release manifest independently as well.
Prefer the signed one-file EXE for a simpler final distribution boundary.

## Optional signed release manifests

Ed25519 signing/verification uses the `cryptography` library; the private key is
never bundled, generated as an application secret, or placed in Git. Normal
protected builds work unsigned. For an independently managed external Ed25519
PEM signing key, the build helper can pin its public key into the native module
and sign the bundled manifest:

```powershell
.venv/Scripts/python.exe scripts/build_release.py --kind protected --layout onefile --output dist/production-release --manifest-signing-key X:/private-release-keys/manifest.private.pem
```

The helper rejects key paths inside this repository. An encrypted PEM can use
`PREVEX_MANIFEST_KEY_PASSWORD` supplied securely to the build process; never put
its value in a script, shell history, CI log or committed environment file.
The helper removes that variable from compiler/packager child environments. Use an appropriately secured build machine/store for this optional operation.
No persistent manifest key was generated for the current release: the user's
selected next step is legitimate **Windows certificate** signing.

`release-manifest.json` separately hashes the **final distributed files**, including
the final EXE. It supports an Ed25519 signature with the same external key if desired.
Publish the manifest or its hash via a trusted independent channel. A verification
key delivered beside a possibly altered download is not an independent trust root.
Keep a trusted raw32-byte public key/fingerprint separately; do not automatically
trust a key in the manifest itself.

```powershell
.venv/Scripts/python.exe scripts/release_integrity.py create dist/production-release --manifest dist/production-release/release-manifest.json
# After obtaining an external signing key, add --signing-key X:/private-release-keys/manifest.private.pem
.venv/Scripts/python.exe scripts/release_integrity.py verify dist/production-release --manifest dist/production-release/release-manifest.json
# Signed verification requires --public-key X:/trusted-public-keys/release.pub
```

Unsigned verification explicitly reports `unsigned`. Signature verification with
an absent/wrong key or a modified signed payload fails. The manifest-creation
step must be repeated **after Authenticode signing**, because signing changes
EXE bytes. The embedded resource manifest is inside the package and is not changed
by signing the outer EXE.

## Optional trusted Windows Authenticode signing

Use a legitimate code-signing certificate (and provider/token/cloud tooling)
issued to the correct legal publisher. A certificate is not purchased or created
by these scripts. A self-signed certificate does **not** automatically establish
Windows trust on another PC. No certificate, private key, PFX, signing password,
or account credential is included in Git or the application. Unsigned development
and unsigned protected builds remain runnable.

Install the certificate/provider using the issuer's procedure on the signing
machine; the certificate/private key should be exposed through its approved
Windows store or hardware token. Use the issuer's cloud-signing client instead
if it does not expose a Windows-store key. The exact cloud workflow depends on
that service and is not implemented by this local certificate-store helper.

After **final packaging** and testing, on a signing workstation with Microsoft's
SignTool already available (normally the Windows SDK):

```powershell
# Use the actual code-signing certificate thumbprint from CurrentUser/My.
# This is the certificate selector; the file signature algorithm is SHA256.
./scripts/Sign-Release.ps1 -Executable dist/production-release/CIC-HMI.exe -CertificateThumbprint YOUR_40_HEX_CERTIFICATE_THUMBPRINT -SignTool 'C:/Program Files (x86)/Windows Kits/10/bin/SDK_VERSION/x64/signtool.exe' -TimestampUrl 'https://YOUR_CERTIFICATE_PROVIDERS_RFC3161_TIMESTAMP_ENDPOINT'

# Equivalent direct signing command (also useful if local policy blocks .ps1 files):
& 'C:/path/to/signtool.exe' sign /sha1 YOUR_40_HEX_CERTIFICATE_THUMBPRINT /fd SHA256 /tr 'https://YOUR_PROVIDERS_TIMESTAMP_ENDPOINT' /td SHA256 dist/production-release/CIC-HMI.exe
# Do not change Windows/PowerShell security policy to run these procedures.

# Independent verification of the final executable:
& 'C:/path/to/signtool.exe' verify /pa /v dist/production-release/CIC-HMI.exe
Get-AuthenticodeSignature dist/production-release/CIC-HMI.exe | Format-List Status,StatusMessage,SignerCertificate

# Regenerate (and optionally sign) the external release manifest LAST:
.venv/Scripts/python.exe scripts/release_integrity.py create dist/production-release --manifest dist/production-release/release-manifest.json
```

Timestamping is recommended so a signature can remain verifiable after certificate
expiry. Signing/timestamping and certificate-revocation checks may require Internet
access on the signing/verification workstation; **the HMI itself has no online
signing, activation or certificate requirement during normal field operation**.
A valid signature does not guarantee SmartScreen reputation or eliminate every
Windows warning. Do not strip, repackage or modify an EXE after signing. Test the
final signed file as well. The user will supply/obtain the legitimate certificate;
no trusted signature is claimed until signing and verification actually succeed.

## Verification and evidence

```powershell
.venv/Scripts/python.exe -m pytest -q --junitxml=tmp/test-results.xml
.venv/Scripts/python.exe scripts/audit_release.py dist/production-release/CIC-HMI.exe
# No analyzer activity; status0 means resource checks passed:
./dist/production-release/CIC-HMI.exe --verify-installation
# Disconnected hardware-only check; use an isolated operator data directory:
./dist/production-release/CIC-HMI.exe --production-smoke-test --data-dir tmp/protected-smoke
```

Run the full source suite with its explicit development harness, native production checks, all four source simulator series,
light/dark About/menu/shortcut/table checks, tamper/missing-resource/signature tests,
PE-icon/archive audits, hardware-only protected startup and isolated development CSV/recording tests. Verify
using a pristine Windows x64 PC without Python before external deployment. Removing
Python from PATH during local packaged testing is useful evidence but is not a
substitute for acceptance on a physically separate clean Windows PC.

A manual `Protected Release` GitHub workflow is provided; it does not replace the
existing development CI. It builds unsigned artifacts, checks disconnected production startup and never
contains signing credentials. Certificates can be applied later on the authorized
signing workstation.

## Evaluation references (primary documentation)

- [Nuitka modes and native package compilation](https://nuitka.net/user-documentation/user-manual.html)
- [Nuitka use cases](https://nuitka.net/user-documentation/use-cases.html)
- [Qt's Nuitka-based deployment support](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
- [PyInstaller spec/data/one-file behavior](https://pyinstaller.org/en/stable/spec-files.html)
- [Cryptography Ed25519 signature API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)
- [Microsoft SignTool signing and verification](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)

Cython pure-Python compilation was also evaluated. Nuitka package compilation was
chosen because it accepts the complete existing package without rewriting Qt
classes, dataclasses, polling logic or register definitions into another language.
The existing packager continues to supply PySide6, PyModbus, PySerial, PyQtGraph,
NumPy, SQLite/CPython and platform DLLs. Actual native tests/package smoke results,
not compilation alone, are required before treating that combination as working.
