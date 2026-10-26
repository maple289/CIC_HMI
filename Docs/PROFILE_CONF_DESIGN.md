# External analyzer profile files: proposed design

Status: design proposal. The current release still loads the existing Python register definitions. This document answers the profile-file question; it does not activate a new loader or change device permissions.

Separate files are a suitable next step for register tables and presentation metadata. Use JSON syntax with a `.conf` extension: the application already uses JSON, values can be checked strictly, and VS Code can provide JSON editing support. Avoid executable Python, expressions, scripts, includes or arbitrary plug-ins in a profile file.

## Files and location

Ship four versioned defaults: `lel_670.conf`, `lel_700.conf`, `btu.conf`, `fid.conf`. Editable copies should live in the application's user-writable `profiles/` directory beside settings.json, outside the installation directory. Defaults must be preserved and distinguishable from user revisions. The profile dropdown should show the file's name, revision, validation scope and whether it has been modified.

The existing analyzer families, legacy FTA handling, 700 variant differences and model/firmware conversion rules must survive export/import exactly. BTU/FID remain preliminary and 700 hardware verification remains pending. User bench evidence for SNR6714.81 does not validate other profiles.

## Data suitable for the files

- Stable profile ID, family, series, revision, source manual/page and documented model applicability.
- Register numbers and descriptions, signedness, units, precision, documented limits/choices and required context.
- Named conversion rules and exact decimal factors/offsets for supported declarative conversions. Complex rules such as legacy dilution and FID FULLSCLE/unit mode need explicit context rather than a single guessed constant.
- Gauge/menu membership, display names and status/relay/service labels with their existing enum-versus-bitfield distinction.
- Documented register pages, read lengths and byte order, subject to the engine's independently enforced supported-protocol constraints.
- Reported validation provenance and unresolved questions, as information rather than an authorization switch.

Illustrative fragment only; not a complete deployable profile:

```json
{
  "schema_version": 1,
  "profile_id": "lel-670",
  "revision": "1.0",
  "family": "LEL",
  "series": "670",
  "registers": [
    {
      "number": 9,
      "name": "Housing temperature",
      "conversion": "temperature",
      "signed": true,
      "unit": "degC",
      "precision": 2,
      "source": "670 SERIES Rev Q, GAUGES menu"
    }
  ]
}
```

## Safeguards that remain application policy

Files must not grant user roles, change passwords, mark identity as verified, authorize hardware or unlock commands by setting a flag. They may restrict permissions but must not expand the application's independently approved physical command scope. Cold Start/internal/prohibited commands, broadcast/address0, generic register-write bypasses and unvalidated physical protocols remain blocked in code. Command words, critical preflight register meanings and valid status/lock rules used for physical control need an independent policy check; editing descriptive labels must not change control decisions.

Reading/conversion edits can still make an instrument display incorrectly. They require authoritative source references and validation; external files are not evidence that a register or protocol is supported. The app should show the active profile revision and store its hash/revision with session/history metadata so old values remain traceable to the conversion used.

## Validation and application

1. Parse JSON as data only. Reject unsupported schema versions, unknown keys, wrong types, duplicate keys/registers, invalid addresses, unsafe ranges, nonfinite numeric values and unsupported conversion identifiers. Boolean values must not be accepted as integer register numbers.
2. Validate model/firmware context, page boundaries, maximum block lengths, signed16-bit representation, enum/bit semantics, inverse quantization and deny rules. Preserve every recorded manual ambiguity.
3. Compare bundled-file output against the existing inventory/conversion/status tests before migrating the runtime. Add invalid-file, modified-permission, wrong-model, missing-context and packaged-offline tests.
4. Offer explicit validation, preview and reload through the application. Do not silently hot-reload a file while monitoring or a command is pending. An active profile change must stop polling, invalidate readings, validate the complete new profile and re-identify the instrument before resuming. Never execute commands as part of reload.
5. Save atomically, retain a known-good revision and audit applied changes. Report invalid edits clearly; do not quietly substitute another register map. First-run default installation can use bundled defaults when no customized file exists.

This approach permits supported register/presentation/conversion changes without rebuilding once the loader is implemented. A genuinely new protocol or conversion algorithm may still require a software update. Migrating the current profiles should be a separate tested change rather than mixing it with account management.
