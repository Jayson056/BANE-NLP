#ifndef JSON_PARSER_H
#define JSON_PARSER_H

#include <string.h>
#include <stdlib.h>

/**
 * Optimized manual JSON value extractor for Webhook payloads.
 * Scans for a key and returns the string value within quotes.
 */
char* extract_json_value(const char* json, const char* key) {
    char search_key[128];
    sprintf(search_key, "\"%s\"", key);
    
    char* key_pos = strstr(json, search_key);
    if (!key_pos) return NULL;
    
    // Move to the colon
    char* colon_pos = strchr(key_pos + strlen(search_key), ':');
    if (!colon_pos) return NULL;
    
    // Move to the opening quote of the value
    char* start_quote = strchr(colon_pos, '\"');
    if (!start_quote) return NULL;
    
    char* end_quote = strchr(start_quote + 1, '\"');
    if (!end_quote) return NULL;
    
    size_t len = end_quote - (start_quote + 1);
    char* value = (char*)malloc(len + 1);
    strncpy(value, start_quote + 1, len);
    value[len] = '\0';
    
    return value;
}

#endif
