#!/bin/bash

SCRIPT_FILE=$(readlink -f $0)

AICODER_MODELS_FILE=/var/run/user/$UID/tmp/models
AICODER_MODEL_CURRENT_FILE=/var/run/user/$UID/tmp/model.cur

echo "Fetching models..."
models=$(aicoder-fetch-models)
if [[ "$?" != 0 ]]; then
    echo "Could not fetch models..."
    exit 1
fi
echo "$models" > "$AICODER_MODELS_FILE"

MODELS=$(<$AICODER_MODELS_FILE)

if [[ "$@" =~ --list ]]; then
    MODEL=$(echo "$MODELS" | fzf -e)
    if [ -z "$MODEL" ]; then
        exit 1
    fi
    IFS=";" read -r API_MODEL CONTEXT_SIZE PROVIDER API_BASE_URL API_KEY _ <<< "$MODEL"
    echo "API_MODEL=$API_MODEL" > $AICODER_MODEL_CURRENT_FILE
    echo "CONTEXT_SIZE=$CONTEXT_SIZE" >> $AICODER_MODEL_CURRENT_FILE
    echo "API_BASE_URL=$API_BASE_URL" >> $AICODER_MODEL_CURRENT_FILE
    echo "API_KEY=$API_KEY" >> $AICODER_MODEL_CURRENT_FILE
fi

tmux display-popup -E "$SCRIPT_FILE --list"
ret=$?
if [ "$ret" != 0 ]; then
    exit 1
fi
cat $AICODER_MODEL_CURRENT_FILE
