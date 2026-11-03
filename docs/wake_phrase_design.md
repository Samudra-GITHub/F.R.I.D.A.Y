# W.E.D.N.E.S.D.A.Y. Wake Phrase Architecture & Privacy Specification

> [!IMPORTANT]
> **Current Status**: **STRICTLY DORMANT / INACTIVE** (`wake_word_active = False`).  
> Always-listening background capture is intentionally deactivated in this implementation. The system operates strictly in user-initiated Push-to-Talk (PTT) mode.

---

## 1. Architectural Overview

The future opt-in wake phrase pipeline for W.E.D.N.E.S.D.A.Y. ("Hey Wednesday") is designed to provide hands-free activation without sacrificing user privacy or system security.

```
+--------------------+        +---------------------------+        +--------------------------+
| Physical Mic Audio | -----> | Ring Buffer in RAM (1.5s) | -----> | Local Offline Wake Engine|
+--------------------+        +---------------------------+        +--------------------------+
                                                                                 |
                                             +-----------------------------------+
                                             | On Keyword Match (> 0.85 Threshold)
                                             v
                                  +-----------------------+
                                  | Transition to LISTENING|
                                  | (Visual Indicator ON) |
                                  +-----------------------+
                                             |
                                             v
                                  +-----------------------+
                                  | Normal PTT STT Pipeline|
                                  | -> Phase 4 Broker Flow |
                                  +-----------------------+
```

---

## 2. Core Privacy Invariants

1. **Explicit User Opt-In Only**:
   - The wake engine is disabled by default on fresh install and startup.
   - Requires explicit toggle by the user in Settings (`voice_wake_phrase_enabled`).
   - If the user toggles it off, microphone capture is torn down immediately.

2. **Zero Ambient Audio Persistence**:
   - Audio is buffered solely in an ephemeral sliding ring-buffer in memory (maximum 1.5 seconds).
   - Audio chunks are continuously overwritten and never written to disk, cache, or external databases.

3. **100% Local Inference**:
   - Keyword spotting is evaluated entirely on-device using a lightweight, open-source offline model (e.g. `openWakeWord` or trained ONNX runtime).
   - Zero audio streams or embeddings are sent to any remote API or cloud provider.

4. **Transparent Visual Feedback**:
   - When the wake-word engine is active, the UI renders an unambiguous status badge: `Listening for "Hey Wednesday"`.
   - The Luminous Orb displays a distinctive idle shimmer.
   - When the keyword triggers, an auditory chime and visual pulse signal the transition to `LISTENING`.

5. **Security Isolation & Capability Invariants**:
   - A wake phrase event **ONLY** transitions the assistant state from `STANDBY` to `LISTENING`.
   - Wake phrase detection **NEVER**:
     - Grants permissions or alters the `SessionPolicy`.
     - Enables location tracking (`LOCATION_CONTROL`).
     - Bypasses the `CapabilityBroker` or server-side parameter validation.
     - Executes destructive or unauthorized tools.

6. **Application Lifecycle Cleanup**:
   - Microphone streams are bound to the component/process lifecycle.
   - When the application is minimized, closed, or put to sleep, all audio recording handles are immediately released (`stream.getTracks().forEach(t => t.stop())`).

---

## 3. Recommended Engine Selection for Future Activation

| Engine | License | Offline | Resource Overhead | Windows 11 Compatibility |
| :--- | :--- | :--- | :--- | :--- |
| **openWakeWord** | Apache-2.0 | Yes | ~50 MB RAM, <2% CPU (ONNX) | Native via `onnxruntime` |
| **Precise** (Mycroft) | Apache-2.0 | Yes | ~80 MB RAM | Requires legacy wheels |
| **Porcupine** | Proprietary / Freemium | Yes | <20 MB RAM | Requires API access key |

**Recommendation**: `openWakeWord` utilizing `onnxruntime` for zero cloud dependency and strict MIT/Apache compliance.
