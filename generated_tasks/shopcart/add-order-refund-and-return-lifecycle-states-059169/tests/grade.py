"""CodeForge verifier grader (stdlib only). Runs inside the Harbor verifier container.

usage: grade.py EXPECTED_JSON FEATURE_JUNIT REGRESSION_JUNIT REWARD_JSON

reward = 1 only if EVERY hidden feature test passed and EVERY pass-to-pass regression test
passed. Missing, skipped, errored or failed tests all count as not passed.
"""

import json
import sys
import xml.etree.ElementTree as ET


def test_id(classname, name):
    return f"{classname}::{name}" if classname else name


def outcomes(path):
    result = {}
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return result
    for case in root.iter("testcase"):
        tid = test_id(case.get("classname", ""), case.get("name", ""))
        if case.find("skipped") is not None:
            result[tid] = "skipped"
        elif case.find("error") is not None:
            result[tid] = "error"
        elif case.find("failure") is not None:
            result[tid] = "failed"
        else:
            result[tid] = "passed"
    return result


def main(argv):
    expected_path, feature_xml, regression_xml, reward_path = argv[1:5]
    with open(expected_path, encoding="utf-8") as fh:
        expected = json.load(fh)
    feature = outcomes(feature_xml)
    regression = outcomes(regression_xml)
    f_ids = expected["feature_tests"]
    r_ids = expected["regression_tests"]
    f_pass = [t for t in f_ids if feature.get(t) == "passed"]
    r_pass = [t for t in r_ids if regression.get(t) == "passed"]
    f_rate = len(f_pass) / len(f_ids) if f_ids else 0.0
    r_rate = len(r_pass) / len(r_ids) if r_ids else 1.0
    reward = 1.0 if f_ids and len(f_pass) == len(f_ids) and len(r_pass) == len(r_ids) else 0.0
    rewards = {"reward": reward, "feature_pass_rate": round(f_rate, 4),
               "regression_pass_rate": round(r_rate, 4)}
    with open(reward_path, "w", encoding="utf-8") as fh:
        json.dump(rewards, fh)
    details = {"rewards": rewards,
               "feature_not_passed": sorted(set(f_ids) - set(f_pass)),
               "regression_not_passed": sorted(set(r_ids) - set(r_pass))}
    with open(reward_path.replace("reward.json", "grading.json"), "w", encoding="utf-8") as fh:
        json.dump(details, fh, indent=2)
    print(json.dumps(rewards))


if __name__ == "__main__":
    main(sys.argv)
