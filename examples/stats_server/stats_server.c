/*
 * stats_server - Central stats collector via Unix socket
 *
 * Listens on a Unix socket, receives JSONL lines, appends to central log.
 * Returns "ok\n" after each successful write.
 *
 * Build: make
 * Run:   ./stats_server
 * Stop:  kill <pid> (or Ctrl-C)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <errno.h>

#define SOCKET_PATH_DEFAULT "/tmp/stats_server.sock"
#define LOG_PATH_ENV "AICODER_CENTRAL_LOG"
#define DEFAULT_LOG_PATH "/home/blah/.aicoder/central_stats.log"
#define BUF_SIZE 65536

static volatile int running = 1;
static int server_fd = -1;
static char socket_path[108];
static char pid_path[512];

static void handle_signal(int sig) {
    (void)sig;
    running = 0;
}

static void cleanup(void) {
    if (server_fd >= 0) {
        close(server_fd);
    }
    unlink(socket_path);
    unlink(pid_path);
}

int main(void) {
    const char *log_path = getenv(LOG_PATH_ENV);
    if (!log_path) log_path = DEFAULT_LOG_PATH;

    /* Resolve socket path */
    const char *tmp_dir = getenv("TMP");
    snprintf(socket_path, sizeof(socket_path), "%s/stats_server.sock",
             tmp_dir ? tmp_dir : "/tmp");
    snprintf(pid_path, sizeof(pid_path), "%s/stats_server.pid",
             tmp_dir ? tmp_dir : "/tmp");

    /* Check for existing instance */
    FILE *pid_fp = fopen(pid_path, "r");
    if (pid_fp) {
        pid_t old_pid;
        if (fscanf(pid_fp, "%d", &old_pid) == 1) {
            if (kill(old_pid, 0) == 0) {
                fprintf(stderr, "[stats_server] Already running (PID %d)\n", old_pid);
                fclose(pid_fp);
                return 1;
            }
        }
        fclose(pid_fp);
        unlink(pid_path);
    }

    /* Write PID file */
    pid_fp = fopen(pid_path, "w");
    if (pid_fp) {
        fprintf(pid_fp, "%d\n", getpid());
        fclose(pid_fp);
    }

    /* Ensure log directory exists */
    char dir[512];
    snprintf(dir, sizeof(dir), "%s", log_path);
    char *slash = strrchr(dir, '/');
    if (slash) {
        *slash = '\0';
        mkdir(dir, 0755);
    }

    FILE *log_fp = fopen(log_path, "a");
    if (!log_fp) {
        perror("fopen log");
        return 1;
    }
    setvbuf(log_fp, NULL, _IONBF, 0);

    /* Remove stale socket */
    unlink(socket_path);

    server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("socket");
        return 1;
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", socket_path);

    if (bind(server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        cleanup();
        return 1;
    }

    chmod(socket_path, 0600);

    if (listen(server_fd, 5) < 0) {
        perror("listen");
        cleanup();
        return 1;
    }

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);
    signal(SIGPIPE, SIG_IGN);

    fprintf(stderr, "[stats_server] Listening on %s\n", socket_path);
    fprintf(stderr, "[stats_server] Writing to %s\n", log_path);

    while (running) {
        int client_fd = accept(server_fd, NULL, NULL);
        if (client_fd < 0) {
            if (errno == EINTR) continue;
            perror("accept");
            continue;
        }

        char buf[BUF_SIZE];
        ssize_t total = 0;
        ssize_t n;

        while (total < BUF_SIZE - 1) {
            n = read(client_fd, buf + total, BUF_SIZE - 1 - total);
            if (n <= 0) break;
            total += n;
            if (memchr(buf, '\n', total)) break;
        }

        if (total > 0) {
            if (buf[total - 1] != '\n') {
                buf[total] = '\n';
                total++;
            }
            buf[total] = '\0';

            /* Check if file was deleted (nlink == 0) */
            struct stat st;
            if (fstat(fileno(log_fp), &st) == 0 && st.st_nlink == 0) {
                fclose(log_fp);
                log_fp = fopen(log_path, "a");
                if (log_fp) setvbuf(log_fp, NULL, _IONBF, 0);
            }

            ssize_t written = log_fp ? (ssize_t)fwrite(buf, 1, total, log_fp) : -1;
            if (written != total && log_fp) {
                /* Retry: reopen and write */
                fclose(log_fp);
                log_fp = fopen(log_path, "a");
                if (log_fp) {
                    setvbuf(log_fp, NULL, _IONBF, 0);
                    written = fwrite(buf, 1, total, log_fp);
                }
            }

            if (written == total) {
                const char *ok = "ok\n";
                write(client_fd, ok, 3);
            } else {
                const char *err = "error: write failed\n";
                write(client_fd, err, strlen(err));
            }
        }

        close(client_fd);
    }

    cleanup();
    fclose(log_fp);
    fprintf(stderr, "[stats_server] Stopped\n");
    return 0;
}
