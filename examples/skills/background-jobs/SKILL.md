---
name: background-jobs
description: Enables AI Coder to run background processes (servers, daemons, services) within the scope of a single shell command execution. Use this skill when testing APIs, web servers, databases, or any services that must be running during test execution. Perfect for integration testing, API endpoint validation, and multi-service orchestration.
---

# Background Jobs

This skill enables AI Coder to orchestrate background processes (servers, daemons, databases) temporarily within a single shell command execution, perform tests against them, and ensure clean shutdown.

## When to Use This Skill

Use this skill when you need to:
- **Test running web servers** - Start an API server and run HTTP tests against it
- **Multi-service integration tests** - Start multiple services (web + database + cache) and test interactions
- **Database-dependent tests** - Start a database server, run migrations, test queries, then shutdown
- **API endpoint validation** - Run a server and verify endpoints with curl/wget
- **Long-running process testing** - Start daemons and verify their behavior
- **Resource validation** - Test services that need time to initialize before interaction

## Core Concept

**AI Coder doesn't support persistent background processes**, but you can achieve similar functionality by:

1. Using `run_shell_command` to execute a bash script
2. Within that script, starting background jobs with `&`
3. Capturing process IDs (PIDs) for lifecycle management
4. Running tests while jobs are running
5. Gracefully shutting down all background processes before script exits

**Key Principle**: All background processes are scoped to the single `run_shell_command` execution and must terminate before the script completes.

## Essential Bash Patterns

### Background Job Execution

```bash
#!/bin/bash

# Start process in background
./server &
PID_SERVER=$!

# Store multiple PIDs
./database &
PID_DB=$!

./cache &
PID_CACHE=$!
```

### Process Lifecycle Management

```bash
#!/bin/bash

echo "Starting servers..."

# Start background jobs
./run_server_1 &
PID_SERVER_1=$!
sleep 3  # Wait for startup

./run_server_2 &
PID_SERVER_2=$!
sleep 2  # Wait for startup

./run_server_3 &
PID_SERVER_3=$!
sleep 10  # Wait for all to be ready

echo "Running tests..."

./run_tests.sh
RESULT=$?

echo "Stopping servers..."

# Graceful shutdown
kill $PID_SERVER_1 $PID_SERVER_2 $PID_SERVER_3
sleep 3

# Force kill if still running
kill -9 $PID_SERVER_1 $PID_SERVER_2 $PID_SERVER_3 2>/dev/null

# Return test results
exit $RESULT
```

### Startup Verification

```bash
#!/bin/bash

# Start server
./server &
PID_SERVER=$!

# Wait for server to be ready
MAX_WAIT=30
COUNTER=0

while ! curl -s http://localhost:8080/health > /dev/null 2>&1; do
    sleep 1
    COUNTER=$((COUNTER + 1))
    
    if [ $COUNTER -ge $MAX_WAIT ]; then
        echo "ERROR: Server did not start within ${MAX_WAIT}s"
        kill $PID_SERVER
        exit 1
    fi
    
    echo "Waiting for server to start... ($COUNTER/$MAX_WAIT)"
done

echo "Server is ready, running tests..."
# Run tests...
```

## Usage Patterns

### Pattern 1: Single Web Server Test

**Use case**: Start a web server and test its endpoints

```bash
#!/bin/bash

set -e  # Exit on error

# Start the web server
echo "Starting web server..."
./server --port 8080 &
PID_SERVER=$!

# Wait for server to be ready
sleep 3

# Verify server is running
if ! ps -p $PID_SERVER > /dev/null; then
    echo "ERROR: Server failed to start"
    exit 1
fi

# Run tests
echo "Running API tests..."
curl -s http://localhost:8080/api/users | grep '"users":' > /dev/null
curl -s http://localhost:8080/api/status | grep '"status": "ok"' > /dev/null
RESULT=$?

# Cleanup
echo "Stopping server..."
kill $PID_SERVER
sleep 2
kill -9 $PID_SERVER 2>/dev/null || true

exit $RESULT
```

### Pattern 2: Multi-Service Integration Test

**Use case**: Test interactions between multiple services

```bash
#!/bin/bash

set -e

echo "Starting services..."

# Start API server
./api_server &
PID_API=$!
sleep 2

# Start database
./database --data-dir /tmp/test_db &
PID_DB=$!
sleep 3

# Start cache
./cache_server &
PID_CACHE=$!
sleep 1

echo "All services started, running integration tests..."

# Run tests
./integration_tests.sh
TEST_RESULT=$?

echo "Stopping all services..."
kill $PID_API $PID_DB $PID_CACHE
sleep 3
kill -9 $PID_API $PID_DB $PID_CACHE 2>/dev/null || true

exit $TEST_RESULT
```

### Pattern 3: Database Migration Test

**Use case**: Test database with migrations and queries

```bash
#!/bin/bash

set -e

echo "Starting test database..."

# Start database in background
./database_server --port 5432 --data /tmp/test_db &
PID_DB=$!

# Wait for database to be ready
sleep 5

# Run migrations
echo "Running migrations..."
./migrate_up --url postgresql://localhost:5432/testdb

# Run tests
echo "Running database tests..."
./db_tests.sh
RESULT=$?

echo "Stopping database..."
kill $PID_DB
sleep 2
kill -9 $PID_DB 2>/dev/null || true

exit $RESULT
```

### Pattern 4: Health Check Before Testing

**Use case**: Ensure services are healthy before running tests

```bash
#!/bin/bash

set -e

# Start services
./server &
PID_SERVER=$!
./database &
PID_DB=$!

# Wait for health checks
MAX_ATTEMPTS=30
for i in $(seq 1 $MAX_ATTEMPTS); do
    # Check server health
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        SERVER_READY=true
    else
        SERVER_READY=false
    fi
    
    # Check database health
    if ./db_check.sh; then
        DB_READY=true
    else
        DB_READY=false
    fi
    
    if [ "$SERVER_READY" = true ] && [ "$DB_READY" = true ]; then
        echo "All services are healthy"
        break
    fi
    
    echo "Waiting for services... ($i/$MAX_ATTEMPTS)"
    sleep 1
done

# Run tests if services are ready
if [ "$SERVER_READY" = true ] && [ "$DB_READY" = true ]; then
    ./run_tests.sh
    RESULT=$?
else
    echo "ERROR: Services failed to become healthy"
    RESULT=1
fi

# Cleanup
kill $PID_SERVER $PID_DB
sleep 2
kill -9 $PID_SERVER $PID_DB 2>/dev/null || true

exit $RESULT
```

## Important Considerations

### Process Management

**ALWAYS capture PIDs** for every background job:
```bash
./command &
PID_VAR=$!
```

**ALWAYS store multiple PIDs** to manage them together:
```bash
kill $PID_1 $PID_2 $PID_3
```

**ALWAYS use graceful shutdown first**:
```bash
kill $PID  # Sends SIGTERM, allows cleanup
sleep 3    # Give time for cleanup
kill -9 $PID  # Force kill if still running
```

### Timing and Startup Delays

Services need time to initialize. Always add appropriate `sleep` commands:

```bash
./server &
PID=$!
sleep 3  # Adjust based on your service startup time
```

For better reliability, use health checks instead of fixed delays (see Pattern 4).

### Error Handling

Use `set -e` to exit on errors:
```bash
#!/bin/bash
set -e  # Exit immediately if any command fails
```

Check if processes started successfully:
```bash
./server &
PID=$!
sleep 2

if ! ps -p $PID > /dev/null; then
    echo "Server failed to start"
    exit 1
fi
```

Always use force kill as fallback:
```bash
kill $PID 2>/dev/null || true
sleep 2
kill -9 $PID 2>/dev/null || true  # Suppress errors if already dead
```

### Timeout Management

When calling these scripts from `run_shell_command`, use appropriate timeouts:

```bash
# Simple tests (30-60 seconds)
run_shell_command "./test_server.sh" timeout=60

# Integration tests (2-5 minutes)
run_shell_command "./integration_test.sh" timeout=300

# Complex multi-service tests (5-10 minutes)
run_shell_command "./full_suite.sh" timeout=600
```

## Best Practices

### DO
- **Always capture PIDs** for every background process
- **Use graceful shutdown first** (kill), then force kill (kill -9)
- **Add startup delays** or health checks before running tests
- **Use `set -e`** to catch errors early
- **Verify services are running** before testing
- **Store test results** and exit with the test result code
- **Clean up in all cases** (success or failure)

### DON'T
- **Don't forget to kill** background processes before script exits
- **Don't assume services start immediately** - add delays/health checks
- **Don't ignore startup failures** - check if PIDs exist
- **Don't let errors propagate silently** - use proper error handling
- **Don't mix foreground and background** - keep them separate
- **Don't skip force kill** - processes might not exit gracefully

## Advanced Techniques

### Output Capture

Capture both server output and test results:

```bash
#!/bin/bash

# Redirect server output to file
./server > server.log 2>&1 &
PID_SERVER=$!
sleep 3

# Run tests
./run_tests.sh > test_results.log 2>&1
RESULT=$?

# Cleanup
kill $PID_SERVER

# Show results if tests failed
if [ $RESULT -ne 0 ]; then
    echo "=== Server Logs ==="
    cat server.log
    echo "=== Test Results ==="
    cat test_results.log
fi

exit $RESULT
```

### Dynamic Service Discovery

Start services dynamically based on configuration:

```bash
#!/bin/bash

# Read services from config
while IFS= read -r service_cmd; do
    echo "Starting: $service_cmd"
    eval $service_cmd &
    PIDS+=" $!"
done < services.conf

sleep 5
./run_tests.sh
RESULT=$?

# Kill all stored PIDs
kill $PIDS 2>/dev/null || true
sleep 2
kill -9 $PIDS 2>/dev/null || true

exit $RESULT
```

### Port Cleanup

Ensure ports are available before starting:

```bash
#!/bin/bash

PORT=8080

# Kill anything already using the port
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
sleep 1

# Start server on clean port
./server --port $PORT &
PID_SERVER=$!
```

## Common Scenarios

### Testing a Python Flask/FastAPI Server

```bash
#!/bin/bash

python app.py &
PID=$!
sleep 3

# Test endpoints
curl http://localhost:5000/api/health | grep "ok"
RESULT=$?

kill $PID
exit $RESULT
```

### Testing a Node.js Server

```bash
#!/bin/bash

node server.js &
PID=$!
sleep 3

npm run test
RESULT=$?

kill $PID
exit $RESULT
```

### Testing with Docker Services

```bash
#!/bin/bash

docker run -d -p 3306:3306 mysql:latest
PID=$(docker ps -q --filter ancestor=mysql)
sleep 10

./run_tests.sh
RESULT=$?

docker stop $PID
docker rm $PID

exit $RESULT
```

## Troubleshooting

### Server doesn't start
- Check if port is already in use
- Verify executable permissions
- Check server logs for errors
- Increase startup delay

### Tests fail intermittently
- Increase sleep times after service startup
- Add health checks before testing
- Check for race conditions in startup

### Processes don't stop
- Verify PID variable is set correctly
- Check if process spawns child processes
- Use `pkill` or `killall` to kill by name if needed

### Port conflicts
- Kill existing processes on the port before starting
- Use random ports instead of fixed ones
- Clean up properly in all exit scenarios

## Keywords

background jobs, background processes, integration testing, API testing, server testing, multi-service testing, process management, bash scripting, daemon testing, web server testing, service orchestration, parallel processes, PID management, graceful shutdown, temporary services, test fixtures
