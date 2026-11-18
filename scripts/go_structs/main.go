// Command go_structs writes, as JSON, the fields of the Go types that Horizon
// serializes its responses from: the types of go-stellar-sdk's protocols/horizon,
// at the version that go.mod pins, which is the one Horizon depends on.
//
// scripts/check_go_structs.py reads the output and compares it with the models.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"sort"
	"strings"
	"time"

	"github.com/stellar/go-stellar-sdk/protocols/horizon"
	"github.com/stellar/go-stellar-sdk/protocols/horizon/effects"
	"github.com/stellar/go-stellar-sdk/protocols/horizon/operations"
)

// Field is one JSON field of a struct, as encoding/json writes it.
type Field struct {
	JSON      string `json:"json"`
	GoName    string `json:"go_name"`
	Kind      string `json:"kind"`
	Type      string `json:"type,omitempty"`
	Elem      string `json:"elem,omitempty"`
	ElemType  string `json:"elem_type,omitempty"`
	OmitEmpty bool   `json:"omitempty"`
	AsString  bool   `json:"string"`
	Pointer   bool   `json:"pointer"`
}

// Struct is one Go struct type.
type Struct struct {
	Marshaler bool    `json:"marshaler"`
	Fields    []Field `json:"fields"`
}

// Output is what the command writes.
type Output struct {
	Version    string            `json:"version"`
	Resources  map[string]string `json:"resources"`
	Operations map[int]string    `json:"operations"`
	Effects    map[int]string    `json:"effects"`
	Structs    map[string]Struct `json:"structs"`
}

var (
	marshaler = reflect.TypeOf((*json.Marshaler)(nil)).Elem()
	timeType  = reflect.TypeOf(time.Time{})
)

func name(t reflect.Type) string {
	if t.Name() == "" {
		return ""
	}
	path := t.PkgPath()
	return path[strings.LastIndex(path, "/")+1:] + "." + t.Name()
}

func implementsMarshaler(t reflect.Type) bool {
	return t.Implements(marshaler) || reflect.PointerTo(t).Implements(marshaler)
}

// opaque types are written by their own code, and are not compared field by field.
func opaque(t reflect.Type) bool {
	return strings.HasSuffix(t.PkgPath(), "/xdr") || (t.Kind() == reflect.Struct && t != timeType && implementsMarshaler(t) && name(t) != "horizon.Transaction")
}

type walker struct {
	structs map[string]Struct
}

func (w *walker) kind(t reflect.Type) (string, string) {
	switch {
	case t == timeType:
		return "time", ""
	case opaque(t):
		return "opaque", name(t)
	}
	switch t.Kind() {
	case reflect.String:
		return "string", ""
	case reflect.Bool:
		return "bool", ""
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return "int", ""
	case reflect.Float32, reflect.Float64:
		return "float", ""
	case reflect.Struct:
		key := name(t)
		if key == "" {
			key = "anonymous"
		} else {
			w.add(t)
		}
		return "struct", key
	case reflect.Slice, reflect.Array:
		return "slice", ""
	case reflect.Map:
		return "map", ""
	case reflect.Interface:
		return "any", ""
	}
	return t.Kind().String(), ""
}

// fields lists the JSON fields of t, with embedded structs promoted as encoding/json does.
func (w *walker) fields(t reflect.Type) []Field {
	var out []Field
	for i := 0; i < t.NumField(); i++ {
		f := t.Field(i)
		tag := f.Tag.Get("json")
		if tag == "-" || (!f.IsExported() && !f.Anonymous) {
			continue
		}
		parts := strings.Split(tag, ",")
		ft := f.Type
		pointer := false
		if ft.Kind() == reflect.Pointer {
			ft, pointer = ft.Elem(), true
		}
		if f.Anonymous && parts[0] == "" && ft.Kind() == reflect.Struct {
			out = append(out, w.fields(ft)...)
			continue
		}
		field := Field{JSON: parts[0], GoName: f.Name, Pointer: pointer}
		if field.JSON == "" {
			field.JSON = f.Name
		}
		for _, option := range parts[1:] {
			field.OmitEmpty = field.OmitEmpty || option == "omitempty"
			field.AsString = field.AsString || option == "string"
		}
		field.Kind, field.Type = w.kind(ft)
		if field.Kind == "slice" || field.Kind == "map" {
			elem := ft.Elem()
			if elem.Kind() == reflect.Pointer {
				elem = elem.Elem()
			}
			field.Elem, field.ElemType = w.kind(elem)
		}
		out = append(out, field)
	}
	return out
}

func (w *walker) add(t reflect.Type) string {
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	key := name(t)
	if _, seen := w.structs[key]; seen {
		return key
	}
	w.structs[key] = Struct{}
	w.structs[key] = Struct{Marshaler: implementsMarshaler(t), Fields: w.fields(t)}
	return key
}

func main() {
	w := &walker{structs: map[string]Struct{}}
	out := Output{
		Resources:  map[string]string{},
		Operations: map[int]string{},
		Effects:    map[int]string{},
	}
	for _, value := range []any{
		horizon.Root{}, horizon.Account{}, horizon.AccountData{}, horizon.AssetStat{},
		horizon.ClaimableBalance{}, horizon.FeeStats{}, horizon.Ledger{},
		horizon.LiquidityPool{}, horizon.Offer{}, horizon.OrderBookSummary{}, horizon.Path{},
		horizon.Trade{}, horizon.TradeAggregation{}, horizon.Transaction{},
		horizon.AsyncTransactionSubmissionResponse{}, horizon.TransactionResultCodes{},
	} {
		key := w.add(reflect.TypeOf(value))
		out.Resources[key] = key
	}
	for typeI := range operations.TypeNames {
		operation, err := operations.UnmarshalOperation(int32(typeI), []byte("{}"))
		if err != nil {
			fmt.Fprintf(os.Stderr, "operation %d: %v\n", typeI, err)
			os.Exit(1)
		}
		out.Operations[int(typeI)] = w.add(reflect.TypeOf(operation))
	}
	for typeI, typeName := range effects.EffectTypeNames {
		effect, err := effects.UnmarshalEffect(typeName, []byte("{}"))
		if err != nil {
			fmt.Fprintf(os.Stderr, "effect %d: %v\n", typeI, err)
			os.Exit(1)
		}
		out.Effects[int(typeI)] = w.add(reflect.TypeOf(effect))
	}
	keys := make([]string, 0, len(w.structs))
	for key := range w.structs {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	out.Structs = w.structs
	if len(os.Args) > 1 {
		out.Version = os.Args[1]
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
