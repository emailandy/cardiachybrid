event_type: defibrillation_shock
detection_priority: [audio_device, visual_patient, speech, monitor]
audio_device:
  charge: "Rising-pitch electronic whine, 1.5–4 s duration, terminating in a steady
           high tone or 'charge ready' chirp. Zoll: ascending warble. LIFEPAK: single
           rising tone + repeating 'ready' beep."
  discharge: "Single sharp click/thunk co-incident with tone cessation. Often followed
              by a short monitor alarm or 'shock delivered' voice prompt."
visual_patient:
  - "Simultaneous whole-body/upper-extremity myoclonic jerk lasting <0.5 s."
  - "All hands visibly off the patient in the 1–3 s before the jerk."
  - "Operator thumb on the orange/red SHOCK button of the defibrillator."
speech:
  precursor: ["charging", "charge to 200", "clear", "I'm clear, you're clear, everybody clear",
              "hands off", "stand back"]
  confirm: ["shock delivered", "shocked", "resume compressions", "back on the chest"]
timestamp_rule: "t = moment of discharge click / myoclonic jerk. NOT the 'clear' call
                 and NOT the charge start."
disambiguation:
  - "A charge with no discharge click and a 'disarm'/'stand down' utterance = NOT a shock. Emit
     event_type=defib_charge_aborted."
  - "Dual sequential defibrillation = two discharges <1.0 s apart from two devices → count as
     ONE shock (num_times_defib_ed_v2) with attributes.dual_sequential=true."
pad_position_rule: "Determine position at the instant of THIS shock, not at initial application.
                    If posterior pad cannot be visualized at any point, and no verbal statement
                    confirms AP, and the anterior-apex pair IS visible → anterolateral.
                    If neither is visible → position=unable_to_determine (code 5). Do not infer
                    from earlier shocks."
abstain_if: "No discharge click AND no myoclonic jerk AND no 'shock delivered' confirmation."

---

event_type: airway_attempt
defining_instants:
  t_start: "First contact of laryngoscope blade OR supraglottic device with the
            lips/teeth. NOT the moment the operator picks up the device. NOT
            pre-oxygenation. NOT OPA/NPA insertion (these are not advanced airways)."
  t_end:   "SUCCESS: first effective ventilation through the placed device —
            visible chest rise on BVM squeeze, or first waveform capnography
            tracing appearing on the monitor, whichever is observable first.
            FAILURE: the instant the blade/device fully exits the mouth."
audio_device:
  - "Suction: loud continuous rushing/gurgling — often signals blood or emesis."
  - "Capnograph alarm state change or first EtCO2 tone after tube placement."
speech:
  attempt_start: ["I'm going in", "blade", "give me the glide", "hold compressions
                  for the tube", "let me take a look"]
  success:  ["I'm in", "through the cords", "tube's in", "hold ETT at 23",
             "bag him", "we have color change", "good CO2"]
  failure:  ["I can't see anything", "coming out", "let's bag", "reposition",
             "I need a bougie", "swap me out"]
  aspiration: ["suction", "he's vomiting", "there's blood", "I've got emesis"]
visual:
  - "Operator positioned at head of bed, patient's head extended, blade entering
     mouth from the patient's right, sweeping left."
  - "Blade type: DL = straight handle + Miller/Mac blade, operator's eyes at the
     patient's mouth. VL = a screen on the handle or a tethered monitor, operator's
     eyes on the SCREEN not the mouth."
  - "Bougie = long thin blue/orange stylet passed before the tube."
  - "SGA = no blade; a single soft-cuffed device inserted blind."
required_attributes:
  device: [endotracheal_DL, endotracheal_VL_hyperangulated, endotracheal_VL_geometric,
           endotracheal_VL_unknown, sga_lma, sga_king, sga_combitube, sga_unknown,
           cricothyrotomy, unable_to_determine]
  adjunct: [bougie, fiberoptic, none, unable_to_determine]
  successful: [true, false, unable_to_determine]
  vomit_blood_aspiration: [true, false, unable_to_determine]
  cpr_ongoing: [true, false, unable_to_determine]      # cross-check sensor track
  compression_type: [manual, mechanical, null]
  operator_position: [head_of_bed, patient_right, patient_left, unable_to_determine]
  operator_pgy: null                                    # ALWAYS null — see rule below
hard_rules:
  - "operator_pgy is ALWAYS null. Training level is not determinable from video.
     Report operator_position only; a roster join resolves PGY downstream."
  - "Insertion and removal of a blade = ONE attempt, even if no tube was passed."
  - "If the operator changes, that is a NEW attempt with its own start time."
  - "VL subtype (hyperangulated vs geometric) requires clear view of the blade
     curvature or an audible product name. Otherwise endotracheal_VL_unknown."
abstain_if: "The mouth and the device are both out of frame for the entire
             candidate interval."

---

event_type: rosc_detected
defining_instants:
  t_start: "The EARLIER of: (a) the first confident verbal declaration of a
            palpable pulse or measurable pressure, or (b) the first frame on
            which the arterial line or plethysmograph shows a pulsatile waveform
            in the ABSENCE of chest compressions (confirm against the compression
            sensor track). Do not use the moment compressions stopped."
speech:
  positive: ["I've got a pulse", "strong femoral", "he's got a pressure",
             "we have ROSC", "pulse is back", "there's a pulse", "sinus on the monitor
              with a pulse"]
  negative_do_not_trigger: ["no pulse", "I don't feel anything", "still no pulse",
             "I think I feel something — no, that's you", "that's the LUCAS"]
audio_device:
  - "SpO2 pulse tone (rhythmic beeping tracking the heartbeat) beginning or
     rising in pitch — strong corroboration."
  - "Monitor alarm state change from asystole/VF alarm to a rate alarm."
monitor_ocr: "HR appears; SpO2 appears; a-line waveform becomes pulsatile;
              EtCO2 typically steps up sharply (often >10 mmHg jump)."
disambiguation:
  - "An EtCO2 rise alone is suggestive, NOT sufficient. Requires a pulse
     statement or a pulsatile arterial waveform."
  - "Compression artifact produces a pulsatile a-line trace. Only count it as
     ROSC if the compression sensor shows compressions are STOPPED."
  - "A pulse felt during ongoing compressions is not ROSC."
required_attributes:
  detection_method: [manual_palpation, ultrasound, arterial_line, monitor_waveform,
                     multiple, unable_to_determine]
  rhythm: [sinus, atrial_fibrillation, junctional, heart_block,
           ventricular_tachycardia, unknown]
  pulse_check_locations: [carotid, femoral, radial, brachial]   # multi-select
abstain_if: "No verbal pulse declaration AND the arterial/pleth trace is not
             legible in the OCR track."
paired_event: "Emit rosc_lost when compressions resume (sensor track) or when
               loss is verbalized. Leave t_end null if ROSC persists to end of video."

---

event_type: vitals_reading
defining_instant: "The timestamp of the monitor frame from which values were read.
                   For an NIBP cuff cycle, use the moment the new value APPEARS,
                   not when the cuff inflated."
source_priority: [monitor_ocr, speech_readout, visual_estimate_PROHIBITED]
hard_rules:
  - "Values come from the monitor_ocr track or a verbatim verbal readout ONLY.
     You may NEVER estimate a numeric value from waveform appearance, patient
     color, or clinical context. If the OCR track has no reading with confidence
     >0.80 within ±15 s and no one read numbers aloud → abstain, all five null."
  - "Each of the five vitals abstains INDEPENDENTLY. A legible HR does not
     license you to guess the SpO2."
  - "Distinguish a-line BP (continuous, ART label) from NIBP (intermittent, NIBP
     label). Record which."
  - "During compressions, displayed HR and SpO2 are artifact. Only report vitals
     tied to a ROSC episode when compressions are confirmed stopped."
required_attributes:
  hr, sbp, dbp, spo2, etco2, bp_source [arterial_line|nibp|unknown],
  linked_rosc_event_id, ocr_confidence
