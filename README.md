# Verilog Align

A Python Tool for aligning Verilog/SystemVerilog.

The tool focuses on improving code readability by aligning declarations, parameters, instance connections, assignments, and other frequently used RTL syntax.

## Features

Currently supports formatting for:

* Input/output ports
* `parameter`
* `localparam`
* `reg`, `wire`, and `logic` declarations
* Module instance connections
* Assignments inside `always`, `always_ff`, and `always_comb`
* Continuous `assign` statements
* `integer` and `genvar`

Tabs are automatically expanded to 4 spaces during formatting.

---

## Requirements

* Python 3
* No external Python packages required

---

## Usage

### Format a single SystemVerilog file

```bash
python align.py design.sv
```

The file will be formatted in place.

### Format a directory

```bash
python align.py ./rtl
```

All `.sv` files under the directory will be searched recursively and formatted.

### Standard input

If no path is specified, the formatter reads from standard input and prints the formatted result to standard output.

```bash
cat design.sv | python align.py
```

On PowerShell:

```powershell
Get-Content design.sv -Raw | python align.py
```

---

## Formatting Options

By default, all formatting features are enabled.

You can enable only specific formatting categories using command-line options:

```text
--io       Align input/output ports
--param    Align parameter and localparam declarations
--signal   Align reg/wire/logic declarations
--inst     Align module instance connections
--assign   Align assignments
--var      Normalize integer/genvar declarations
```

For example:

```bash
python align.py design.sv --io
```

Only IO ports will be formatted.

Multiple options can be combined:

```bash
python align.py design.sv --io --signal --inst
```

---

## Excluding Formatting Categories

Use `--exclude` when you want to run all formatters except selected ones.

For example:

```bash
python align.py design.sv --exclude assign
```

This runs all formatting features except assignment alignment.

Multiple categories can be excluded:

```bash
python align.py design.sv --exclude assign inst
```

Available categories:

```text
io
param
signal
inst
assign
var
```

---

## Examples

### IO Alignment

Before:

```systemverilog
input clk,
input rst_n,
input [31:0] data_in,
output [7:0] result,
output logic valid
```

After:

```systemverilog
input               clk,
input               rst_n,
input        [31:0] data_in,
output       [7:0]  result,
output logic        valid
```

---

### Parameter Alignment

Before:

```systemverilog
parameter DATA_WIDTH = 32,
parameter ADDR_WIDTH = 16,
parameter ID = 0
```

After:

```systemverilog
parameter DATA_WIDTH = 32,
parameter ADDR_WIDTH = 16,
parameter ID         = 0
```

`localparam` declarations are also supported.

---

### Signal Declaration Alignment

Before:

```systemverilog
wire data_valid;
logic [31:0] data;
reg [7:0] state;
```

After:

```systemverilog
wire         data_valid;
logic [31:0] data;
reg   [7:0]  state;
```

---

### Instance Connection Alignment

Before:

```systemverilog
.u_clk(clk),
.u_reset_n(rst_n),
.u_data(data)
```

After:

```systemverilog
.u_clk     (clk),
.u_reset_n (rst_n),
.u_data    (data)
```

---

### Assignment Alignment

Before:

```systemverilog
always_ff @(posedge clk) begin
    counter <= counter + 1;
    data_valid <= 1'b1;
    state <= NEXT_STATE;
end
```

After:

```systemverilog
always_ff @(posedge clk) begin
    counter    <= counter + 1;
    data_valid <= 1'b1;
    state      <= NEXT_STATE;
end
```

Continuous assignments are also aligned:

```systemverilog
assign output_data  = internal_data;
assign output_valid = internal_valid;
```

---

## Command-Line Help

```bash
python align.py --help
```

Example:

```text
usage: align.py [-h]
                [--io]
                [--param]
                [--signal]
                [--inst]
                [--assign]
                [--var]
                [--exclude {io,param,signal,inst,assign,var} [...]]
                [path]
```

---

## Notes

The tool modifies files **in place** when a file or directory path is provided.
When a directory is provided, the current implementation recursively processes `.sv` or `.v` files.

---

## License

This project is available for personal and development use.
