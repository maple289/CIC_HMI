# Command readiness after sign-in

## Current connected controller

**User bench verification,2026-10-25:** the user confirms that all available operating commands worked on the real SNR671 firmware4.81 controller after simulating normal flame temperature and flow inputs. Command operation on this bench setup is now USER BENCH-VERIFIED. This confirmation does not establish all-register/other-model support, calibration accuracy, save retention across power cycles or every lock condition. Existing role/confirmation/controller checks remain unchanged. See VERIFICATION.md for scope and evidence provenance.

The observed identity is `TYPE FTA ... SNR671`, with provisional firmware interpretation `4.81` from bytes `4 A7 81`. The supplied **670 SERIES Rev Q** explicitly says on PDF page2 and printed page2 (Software Versions) that it covers **5.12 and above**. Its register8 command table does not establish compatibility with4.81.

On 2026-10-24 the user explicitly instructed that 4.81 use the 5.12 register/command map despite unavailable 4.81 documentation. Recognized 670 models with firmware4.81 now have all eleven documented operating commands, subject to role, confirmation, fresh matching identity, lock/status and pending-command checks. The legacy LCD/measurement subset remains intact; CAL LOCK60 is read using the approved compatibility assumption. A zero lock value is interpreted under that assumption, not presented as independently verified register support. The agent issued no real commands during development/testing; the subsequent user bench confirmation above verifies command operation on the observed SNR671 setup. Broader compatibility, calibration accuracy, persistence and detailed lock coverage still need validation.

Rev Q's serial identification table also prints `VER5.11` as an example despite the cover/Software Versions scope saying5.12+. That inconsistency is recorded rather than treated as proof of4.81 command/lock compatibility. The software does not claim that the older commands differ; their applicability is unverified.

## Current controls

| Connection / role | Available controls |
| --- | --- |
| Normal documented6705.12-5.x, Administrator | All eleven documented operating buttons available after sign-in, subject to current lock/status checks and individual confirmation |
| Normal documented6705.12-5.x, Operator | Same controls except persistent SAVE ALL requires Administrator |
| Recognized6704.81, Administrator | All eleven commands using the user-approved5.12 map; each requires confirmation and preflight checks |
| Recognized6704.81, Operator | Same except SAVE ALL requires Administrator |
| Other normal hardware connections | Read-only monitoring until the applicable command/firmware behavior is verified |
| Connected SNR671 COM4/9600/address1, Operator/Administrator | Normal Connect or **Connect SNR671 / COM4** offers the user-approved4.81 operating set after sign-in; connection sends no command |
| Simulation, Operator/Administrator, matching identity and valid lock state | Documented commands for the selected profile; unavailable commands retain their manufacturer restrictions |
| Viewer or disconnected/unresolved target | Commands disabled with a visible explanation |

The Commands panel displays readiness and the4.81 compatibility assumption above the command list. No separate bench activation is needed for the recognized4.81 operating set.

## Approved documented-firmware expansion

The user explicitly approved expanding physical controls for manufacturer-validated firmware. AGENTS.md now records that instruction. An initial proposal was rejected under the prior ACK/RESET-only rule; no rejected writer was installed. The approved implementation uses a separate, fixed-command transport with matching model/firmware/endpoint scope, activated only after a role-checked and confirmed command request. Ordinary Connect and sign-in alone never send a command or construct that transport.

The implemented allowlist is register8 only:0300/0400/0500 calibration,0600/0700/0800 tests,0900 save,0F00 lock and1000 unlock, plus0100/0200 operator actions. It excludes Cold Start, internal/remote-menu commands, output-test bypasses and generic register writes. Controls require fresh matching identity, documented firmware or the explicit4.81 assumption, current role, explicit target confirmation, valid lock/busy preflight, serialized single transmission, no ambiguous retries, audit and separate STATUS outcome monitoring. Save explicitly warns about EEPROM persistence. Acknowledgment never proves persistence or calibration success. Software unlock does not bypass a hardware lock.

The implementation accepts recognized670 assemblies with firmware5.12 through5.x and the specifically approved4.81 version; other unknown firmware remains restricted. It rechecks identity/status/locks after switching from the read-only transport, before transmitting. One serial owner closes the old handle before opening the scoped transport. Calibration start and terminal STATUS observations are audited separately. Timeout derives from documented1-4minute calibration intervals, with full zero/span sequences allowed two intervals plus recovery margin.

The user subsequently specifically authorized calibration/test writes during fault states. A documented fault STATUS alone no longer blocks these controls. The active fault appears in the target confirmation and remains visible. Controller locks, role, firmware compatibility, communication and busy/pending checks still apply. A pre-existing fault remaining unchanged after acknowledgment is not proof of failure or success: one WAITING_STATUS event is recorded, the HMI continues to watch for a fresh execution sequence, and unresolved timeout becomes UNKNOWN with no retry. Undocumented/invalid STATUS data is still rejected.

This implementation does not verify4.81 firmware. Its additional writes are enabled by the explicit user-approved compatibility assumption; physical behavior still needs validation. Rev D700 Lock/Unlock have no Modbus effect, and Save permits factory changes; those restrictions cannot be removed merely to light up every button.700 physical control validation remains pending. New operating writes are tested with fake clients only; no real command was executed during development.


## Confirmed card adjustments (2026-10-26)

The user explicitly authorized physical CAL TIME28, SPAN temperature56, WARNING5, DANGER6 and Warning/Danger/Fault/Horn LATCHES17 for signed-in Operator/Administrator users, including the existing670 firmware4.81 map assumption. This is authorization for future user-confirmed actions, not manufacturer/hardware validation and not permission for the agent to exercise a real command during development/testing.

Each request requires current communication, fresh matching identity, unchanged target value, valid/unlocked CAL LOCK60, known/not-busy STATUS, documented ranges and valid WARNING<DANGER ordering. After the scoped transport activates, identity and preflight values are read again. Session permission is revalidated immediately before audit/send. Exactly one named FC06 setting write is sent on the existing paced bus owner, followed by FC03 verification. Unknown acknowledgment/readback outcomes block commands/adjustments until reconnect; there is no automatic retry. SAVE ALL remains separate and Administrator-only. Guest/Viewer and password-rotation-restricted accounts remain read-only.

FAILSAFE18 remains explicitly prohibited for Modbus writes. No other parameter or command-register bypass is introduced.700/BTU/FID physical setting writes remain unavailable. Automated tests use fake SDK clients only.
