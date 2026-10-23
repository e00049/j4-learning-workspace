FROM golang:1.22 AS build
RUN CGO_ENABLED=0 go install github.com/rakyll/hey@v0.1.4
FROM gcr.io/distroless/static:nonroot
COPY --from=build /go/bin/hey /hey
ENTRYPOINT ["/hey"]
