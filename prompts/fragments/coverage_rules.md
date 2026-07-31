## COVERAGE NOTES ARE LOAD-BEARING
Downstream logic distinguishes "this did not happen" (No) from "this could not
be observed" (Unable to determine) SOLELY from your `coverage_notes`. If you
omit a note for an interval you could not observe, the system will assert a
false negative into a clinical research database.
Emit a coverage_note for every interval where any of these applied, using the
exact issue codes:
  chest_occluded | monitor_not_visible | airway_not_visible |
  audio_unintelligible | camera_motion | provider_crowding | frame_dropout
Be liberal. An over-reported coverage gap costs a human 30 seconds of review.
An under-reported one corrupts the dataset permanently.