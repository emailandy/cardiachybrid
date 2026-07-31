## TIMESTAMP PRECISION DRIVES HUMAN REVIEW
`t_precision_s` is your honest uncertainty half-width, and it is consumed by an
automated router: values above threshold are queued for human verification.
Understating precision does not make you look confident — it routes a bad
timestamp straight into the database. Overstating it costs a human 30 seconds.
Calibration guide:
  0.2   sensor-anchored instant (discharge click, motion-track boundary)
  0.5   crisp visual instant at 5 fps (blade contacts teeth)
  1.0   clear visual instant at 2 fps
  2.0   inferred from a verbal statement that may lag the act
  3.0+  boundary of a gradual or partially occluded process
When ensemble runs disagree by more than 3 seconds, the field is routed to a
human regardless of your stated confidence.