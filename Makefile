APP := aprd

.PHONY: build install run clean tidy ci

build:
	go mod tidy
	mkdir -p bin
	go build -o bin/$(APP) ./cmd/aprd

install: build
	install -m 0755 bin/$(APP) /usr/local/bin/$(APP)

run: build
	./bin/$(APP)

clean:
	rm -rf bin

tidy:
	go mod tidy

ci:
	go test ./...
