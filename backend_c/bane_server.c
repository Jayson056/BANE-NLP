#include <stdio.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <process.h>

#pragma comment(lib, "ws2_32.lib")

#define PORT "8080"
#define BUFFER_SIZE 8192

#include "router_bridge.c"
#include "bane_logger.c"
#include "security_layer.c"

void handle_client(void* socket_ptr) {
    SOCKET client_socket = *(SOCKET*)socket_ptr;
    free(socket_ptr);

    char buffer[BUFFER_SIZE];
    int bytes_received = recv(client_socket, buffer, BUFFER_SIZE - 1, 0);
    
    if (bytes_received > 0) {
        buffer[bytes_received] = '\0';
        
        log_native("SERVER", "Incoming request received");

        if (strncmp(buffer, "GET", 3) == 0) {
            if (validate_messenger_token(buffer)) {
                log_native("SECURITY", "Messenger token validated successfully");
                
                // Extract hub.challenge from query string
                char* challenge_ptr = strstr(buffer, "hub.challenge=");
                if (challenge_ptr) {
                    challenge_ptr += 14; // Move past "hub.challenge="
                    char challenge[256] = {0};
                    int i = 0;
                    while (challenge_ptr[i] != ' ' && challenge_ptr[i] != '&' && challenge_ptr[i] != '\0' && i < 255) {
                        challenge[i] = challenge_ptr[i];
                        i++;
                    }
                    
                    char challenge_res[512];
                    sprintf(challenge_res, "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n%s", challenge);
                    send(client_socket, challenge_res, (int)strlen(challenge_res), 0);
                    log_native("SECURITY", "Sent hub.challenge back to Facebook");
                } else {
                    const char* ok_res = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nBANE_READY";
                    send(client_socket, ok_res, (int)strlen(ok_res), 0);
                }
            } else {
                const char* fail_res = "HTTP/1.1 403 Forbidden\r\n\r\nInvalid Token";
                send(client_socket, fail_res, (int)strlen(fail_res), 0);
            }
        } else if (strncmp(buffer, "POST", 4) == 0) {
            char* body = strstr(buffer, "\r\n\r\n");
            if (body) {
                body += 4;
                log_native("ROUTER", "Routing POST payload to Python bridge");
                forward_to_python_engine(body);
            }
            const char* response = 
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                "Connection: close\r\n"
                "\r\n"
                "{\"status\":\"PROXIED_BY_BANE_C\"}";
            send(client_socket, response, (int)strlen(response), 0);
        }
    }

    closesocket(client_socket);
    _endthread();
}

int main() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        printf("WSAStartup failed.\n");
        return 1;
    }

    struct addrinfo *result = NULL, hints;
    ZeroMemory(&hints, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    hints.ai_flags = AI_PASSIVE;

    getaddrinfo(NULL, PORT, &hints, &result);

    SOCKET listen_socket = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    bind(listen_socket, result->ai_addr, (int)result->ai_addrlen);
    listen(listen_socket, SOMAXCONN);

    printf("BANE NLP C-Backend Listening on Port %s...\n", PORT);

    while (1) {
        SOCKET client_socket = accept(listen_socket, NULL, NULL);
        if (client_socket != INVALID_SOCKET) {
            SOCKET* socket_ptr = malloc(sizeof(SOCKET));
            *socket_ptr = client_socket;
            _beginthread(handle_client, 0, socket_ptr);
        }
    }

    closesocket(listen_socket);
    WSACleanup();
    return 0;
}
