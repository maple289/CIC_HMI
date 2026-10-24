# Command readiness after sign-in

## Current connected controller

The observed identity is `TYPE FTA ... SNR671`, with provisional firmware interpretation `4.81` from bytes `4 A7 81`. The supplied **670 SERIES Rev Q** explicitly says on PDF page2 and printed page2 (Software Versions) that it covers **5.12 and above**. Its register8 command table does not establish compatibility with4.81.

The older FTA subset intentionally excludes CAL LOCK60 because its support on this controller is unverified. A zero reply from an unsupported register must not be treated as proof that calibration is unlocked. Existing read-only bench tests do not verify calibration, save/persistence or lock commands.

Rev Q's serial identification table also prints `VER5.11` as an example despite the cover/Software Versions scope saying5.12+. That inconsistency is recorded rather than treated as proof of4.81 command/lock compatibility. The software does not claim that the older commands differ; their applicability is unverified.

## Current controls

| Connection / role | Available controls |
| --- | --- |
| Normal documented6705.12-5.x, Administrator | All eleven documented operating buttons available after sign-in, subject to current lock/status checks and individual confirmation |
| Normal documented6705.12-5.x, Operator | Same controls except persistent SAVE ALL requires Administrator |
| Other normal hardware connections | Read-only monitoring until the applicable command/firmware behavior is verified |
| Connected SNR671 COM4/9600/address1, Operator/Administrator | Explicit **Enable Acknowledge / Reset** action opens the existing approved bench session; it sends no command by itself |
| Approved bench session, Operator/Administrator | Acknowledge and Reset, each with target confirmation and audit |
| Simulation, Operator/Administrator, matching identity and valid lock state | Documented commands for the selected profile; unavailable commands retain their manufacturer restrictions |
| Viewer or disconnected/unresolved target | Commands disabled with a visible explanation |

The Commands panel now puts the access reason and bench activation action above the command list. It reports the older-firmware documentation gap instead of leaving unexplained disabled buttons.

## Approved documented-firmware expansion

The user explicitly approved expanding physical controls for manufacturer-validated firmware. AGENTS.md now records that instruction. An initial proposal was rejected under the prior ACK/RESET-only rule; no rejected writer was installed. The approved implementation uses a separate, fixed-command transport with matching model/firmware/endpoint scope, activated only after a role-checked and confirmed command request. Ordinary Connect and sign-in alone never send a command or construct that transport.

The implemented allowlist is register8 only:0300/0400/0500 calibration,0600/0700/0800 tests,0900 save,0F00 lock and1000 unlock, plus0100/0200 operator actions. It excludes Cold Start, internal/remote-menu commands, output-test bypasses and generic register writes. Controls require fresh matching identity, documented firmware, current role, explicit target confirmation, valid lock/busy preflight, serialized single transmission, no ambiguous retries, audit and separate STATUS outcome monitoring. Save explicitly warns about EEPROM persistence. Acknowledgment never proves persistence or calibration success. Software unlock does not bypass a hardware lock.

The implementation accepts recognized670 assemblies with firmware5.12 through5.x; unknown major versions are not guessed. It rechecks identity/status/locks after switching from the read-only transport, before transmitting. One serial owner closes the old handle before opening the scoped transport. Calibration start and terminal STATUS observations are audited separately. Timeout derives from documented1-4minute calibration intervals, with full zero/span sequences allowed two intervals plus recovery margin.

The user subsequently specifically authorized calibration/test writes during fault states. A documented fault STATUS alone no longer blocks these controls. The active fault appears in the target confirmation and remains visible. Controller locks, role, firmware compatibility, communication and busy/pending checks still apply. A pre-existing fault remaining unchanged after acknowledgment is not proof of failure or success: one WAITING_STATUS event is recorded, the HMI continues to watch for a fresh execution sequence, and unresolved timeout becomes UNKNOWN with no retry. Undocumented/invalid STATUS data is still rejected.

This implementation does not verify4.81 firmware. For that controller, obtain an applicable command/lock specification or manufacturer confirmation before enabling the additional writes. Rev D700 Lock/Unlock have no Modbus effect, and Save permits factory changes; those restrictions cannot be removed merely to light up every button.700 physical control validation remains pending. New operating writes are tested with fake clients only; no real command was executed during development.
