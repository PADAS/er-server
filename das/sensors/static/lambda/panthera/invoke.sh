PROJECT_DIR=$PWD
PROFILE='DAS'
REGION='us-west-2'

aws lambda invoke \
--invocation-type Event \
--function-name panthera-camera-trap \
--region $REGION \
--payload file:/$PROJECT_DIR /inputfile.txt \
--profile $PROFILE \
outputfile.txt