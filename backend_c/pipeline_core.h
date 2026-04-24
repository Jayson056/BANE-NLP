#ifndef PIPELINE_CORE_H
#define PIPELINE_CORE_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char* sender_id;
    char* raw_text;
    char* context;
    char* plan;
    char* final_response;
} BaneTask;

// Function prototypes for the 7 layers
void layer1_intake(BaneTask* task);
void layer2_context(BaneTask* task);
void layer3_planner(BaneTask* task);
void layer4_composer(BaneTask* task);
void layer5_bridge(BaneTask* task);
void layer6_handler(BaneTask* task);
void layer7_renderer(BaneTask* task);

#endif
