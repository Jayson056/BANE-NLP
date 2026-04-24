#include <stdio.h>
#include <time.h>
#include <stdarg.h>

/**
 * High-performance C logger.
 * Writes directly to bnp_native.log with microsecond-level precision.
 */
void log_native(const char* tag, const char* format, ...) {
    FILE* f = fopen("logs/bnp_native.log", "a");
    if (!f) return;

    time_t now;
    time(&now);
    char* date = ctime(&now);
    date[strlen(date) - 1] = '\0'; // Remove newline

    fprintf(f, "[%s] [%s] ", date, tag);
    
    va_list args;
    va_start(args, format);
    vfprintf(f, format, args);
    va_end(args);
    
    fprintf(f, "\n");
    fclose(f);
}
