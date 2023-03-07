#!/bin/bash

function echo_b() {
  echo "";
  echo ">>> ===============================================";
  echo ">>> $1";
  echo ">>> ===============================================";
}

function review_results() {
  if grep -i 'failures="0"' /testresults/result.xml; then
    echo "Suite executed successfully"
  else
    exit 1
  fi
}

function run_test_suite_one() {
  echo_b "Running test suite one...";
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 accounts/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 mapping/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 reports/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 rt_api/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 tracking/tests
  review_results
}

function run_test_suite_two() {
  echo_b "Running test suite two...";
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 activity/tests
  review_results
}

function run_test_suite_three() {
  echo_b "Running test suite three...";
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 analyzers/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 utils/tests
  review_results
}

function run_test_suite_four() {
  echo_b "Running test suite four...";
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 choices/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 das_server/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 observations/tests
  review_results
  pytest --create-db --junitxml=/testresults/result.xml --maxfail=15 core/tests
  review_results
}

. $(dirname "$0")/../start_scripts/wait_for.sh
wait_for $DB_HOST $DB_PORT

export PYTHONPATH=$(dirname "$0"):$PYTHONPATH

python3 -m pip install --upgrade keyrings.alt
python3 -m pip install -r /workspace/dependencies/requirements-dev.txt \
   --find-links /workspace/dependencies/wheelhouse/ --upgrade

export DJANGO_SETTINGS_MODULE=unittest_settings

echo "${CIRCLE_NODE_TOTAL}"
echo "${CIRCLE_NODE_INDEX}"

# Execute based on number of Circle CI nodes, and which Circle CI node is running
case "$CIRCLE_NODE_TOTAL" in
  "")
    echo_b "Will run all tests";
    run_test_suite_one &&
    run_test_suite_two &&
    run_test_suite_three &&
    run_test_suite_four;
    ;;
  1 )
    # This case is triggered when there is only one Circle CI node, or when run locally
    echo_b "Will run all tests";
    run_test_suite_one &&
    run_test_suite_two &&
    run_test_suite_three &&
    run_test_suite_four;
    ;;
  2 )
    # This case is triggered when there are two Circle CI nodes
    case $CIRCLE_NODE_INDEX in
      0 )
        # These commands will run on the first Circle CI node
        echo_b "Will run linter, test suite one, and test suite two";
        run_test_suite_one &&
        run_test_suite_two;
        ;;
      1 )
        # These commands will run on the second Circle CI node
        echo_b "Will run test suite three and test suite four";
        run_test_suite_three &&
        run_test_suite_four;
        ;;
    esac
    ;;
  3 )
    # This case is triggered when there are three Circle CI nodes
    case $CIRCLE_NODE_INDEX in
      0 )
        # These commands will run on the first Circle CI node
        echo_b "Will run linter, test suite one, and test suite two";
        run_test_suite_one &&
        run_test_suite_two;
        ;;
      1 )
        # These commands will run on the second Circle CI node
        echo_b "Will run test suite three";
        run_test_suite_three;
        ;;
      2 )
        # These commands will run on the third Circle CI node
        echo_b "Will run test suite four";
        run_test_suite_four;
        ;;
    esac
    ;;
  * )
    # This case is triggered when there are four or more Circle CI nodes
    case $CIRCLE_NODE_INDEX in
      0 )
        # These commands will run on the first Circle CI node
        echo_b "Will run linter and test suite one";
        run_test_suite_one;
        ;;
      1 )
        # These commands will run on the second Circle CI node
        echo_b "Will run test suite two";
        run_test_suite_two;
        ;;
      2 )
        # These commands will run on the third Circle CI node
        echo_b "Will run test suite three";
        run_test_suite_three;
        ;;
      3 )
        # These commands will run on the fourth Circle CI node
        echo_b "Will run test suite four";
        run_test_suite_four;
        ;;
      * )
        # This warning will display on the fifth or any later Circle CI node
        echo_b "We only split tests across a maximum of 4 nodes";
        exit 0;
    esac
    ;;
esac
