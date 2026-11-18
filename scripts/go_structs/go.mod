// The go-stellar-sdk version is the one that Horizon's go.mod requires, for the release in
// stellar_horizon.HORIZON_VERSION. Raise both together; dependabot does not manage it.
module github.com/lightsail-network/py-stellar-horizon/scripts/go_structs

go 1.25.0

require github.com/stellar/go-stellar-sdk v0.9.0

require (
	github.com/go-chi/chi v4.1.2+incompatible // indirect
	github.com/go-errors/errors v1.5.1 // indirect
	github.com/gorilla/schema v1.4.1 // indirect
	github.com/klauspost/compress v1.17.6 // indirect
	github.com/pkg/errors v0.9.1 // indirect
	github.com/segmentio/go-loggly v0.5.1-0.20171222203950-eb91657e62b2 // indirect
	github.com/sirupsen/logrus v1.9.3 // indirect
	github.com/stellar/go-xdr v0.0.0-20260806060815-dc590f17552a // indirect
	golang.org/x/sys v0.47.0 // indirect
)
