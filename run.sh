#!/bin/bash
export $(egrep -v '^#' .env | xargs)
supervisord -n