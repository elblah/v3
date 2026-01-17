#!/bin/bash

SCRIPT_FILE=$(readlink -f $0)

AICODER_MODELS_FILE=/run/user/$UID/tmp/models
AICODER_MODEL_CURRENT_FILE=/run/user/$UID/tmp/model.cur

if [ ! -e "$AICODER_MODELS_FILE" ]; then
    # NOTE: aicoder-gen-models is not provided by aicoder and 
    #       should be implemented by the user
    echo "No models file found... execute aicoder-gen-models"
    exit 1
fi

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
