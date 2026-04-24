#include <string.h>
#include <stdbool.h>

#define MESSENGER_VERIFY_TOKEN "bane_messenger_secure_777"

/**
 * Fast security check for Facebook Webhook verification.
 */
bool validate_messenger_token(const char* query_params) {
    if (strstr(query_params, "hub.verify_token=") && strstr(query_params, MESSENGER_VERIFY_TOKEN)) {
        return true;
    }
    return false;
}

/**
 * Basic IP rate limiting (simplified).
 * In a real C backend, this would use a hash map.
 */
bool check_rate_limit(const char* ip_address) {
    // For now, always return true. 
    // Future: Track IP timestamps in a static array.
    return true;
}
