import re

with open("tests/test_union_ensemble.py", "r") as f:
    content = f.read()

# Replace the specific lines
old_lines = """    with patch("scripts.run_case.assemble_submission"):
        with patch("scripts.run_case.reduce_stream") as mock_reduce:
            mock_reduce.return_value = ([], [], [])
            run_live(args, duration_s=1363.78)"""

new_lines = """    with patch("scripts.run_case.reduce_stream") as mock_reduce:
        mock_reduce.return_value = ([], [], [])
        run_live(args, duration_s=1363.78)"""

content = content.replace(old_lines, new_lines)

with open("tests/test_union_ensemble.py", "w") as f:
    f.write(content)
