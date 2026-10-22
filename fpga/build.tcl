# Full Vivado only. Lab Edition cannot synthesize or implement this design.
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build ypcb vivado [clock format [clock seconds] -format %Y%m%dT%H%M%S]]
file mkdir $out
set part xc7k480tffg1156-2
set led_active_low 0
if {[info exists ::env(TINYGPU_LED_ACTIVE_LOW)]} { set led_active_low $::env(TINYGPU_LED_ACTIVE_LOW) }
if {$led_active_low ni {0 1}} { error "TINYGPU_LED_ACTIVE_LOW must be 0 or 1" }
set emit 0
if {[info exists ::env(TINYGPU_EMIT_BITSTREAM)]} { set emit $::env(TINYGPU_EMIT_BITSTREAM) }
if {$emit ni {0 1}} { error "TINYGPU_EMIT_BITSTREAM must be 0 or 1" }
set clock_iostandard LVCMOS18
if {[info exists ::env(TINYGPU_CLOCK_IOSTANDARD)]} {
    set clock_iostandard $::env(TINYGPU_CLOCK_IOSTANDARD)
}
if {$clock_iostandard ni {LVCMOS18 LVCMOS33}} {
    error "TINYGPU_CLOCK_IOSTANDARD must be LVCMOS18 or LVCMOS33"
}
if {$emit} {
    foreach name {TINYGPU_CONFIG_VOLTAGE TINYGPU_CFGBVS TINYGPU_CLOCK_IOSTANDARD} {
        if {![info exists ::env($name)]} { error "Supply board-verified $name before emitting a bitstream" }
    }
    set voltage $::env(TINYGPU_CONFIG_VOLTAGE)
    set cfgbvs $::env(TINYGPU_CFGBVS)
    if {$voltage ni {1.5 1.8 2.5 3.3} || $cfgbvs ni {GND VCCO}} { error "Invalid configuration voltage/CFGBVS" }
    if {($voltage in {1.5 1.8} && $cfgbvs ne "GND") || ($voltage in {2.5 3.3} && $cfgbvs ne "VCCO")} {
        error "Incompatible configuration voltage/CFGBVS pair"
    }
}
create_project -in_memory -part $part
# sv2v conversion handles the upstream SystemVerilog's unpacked-array resets.
set converted [file join $root build ypcb vivado-input.v]
set sources [concat [glob [file join $root src *.sv]] [glob [file join $root fpga rtl *.sv]]]
exec sv2v -I [file join $root fpga generated] {*}$sources > $converted
read_verilog $converted
read_xdc [file join $root fpga ypcb.xdc]
synth_design -top ypcb_tiny_gpu_top -part $part -generic LED_ACTIVE_LOW=$led_active_low
set_property IOSTANDARD $clock_iostandard [get_ports SYS_CLK]
if {$emit} {
    set_property CONFIG_VOLTAGE $voltage [current_design]
    set_property CFGBVS $cfgbvs [current_design]
}
if {[llength [get_cells -hierarchical -filter {REF_NAME == RAMB18E1 || REF_NAME == RAMB36E1}]] < 2} {
    error "Program and data memory did not both map to BRAM"
}
write_checkpoint -force [file join $out synthesized.dcp]
opt_design
place_design
phys_opt_design
route_design
if {[get_property IOSTANDARD [get_ports SYS_CLK]] ne $clock_iostandard} {
    error "Clock I/O standard was not retained after routing"
}
set electrical_report [open [file join $out electrical.txt] w]
puts $electrical_report "Clock I/O standard: $clock_iostandard; explicit selection: [info exists ::env(TINYGPU_CLOCK_IOSTANDARD)]"
puts $electrical_report "Values supplied by caller; actual board voltages and straps require verification."
if {$emit} {
    puts $electrical_report "CONFIG_VOLTAGE: $voltage; CFGBVS: $cfgbvs"
}
close $electrical_report
write_checkpoint -force [file join $out routed.dcp]
report_utilization -file [file join $out utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out timing.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_drc -file [file join $out drc.rpt]
foreach kind {max min} {
    set paths [get_timing_paths -delay_type $kind -max_paths 1]
    if {[llength $paths] == 0} { error "No $kind timing paths; inspect constraints" }
    set slack [get_property SLACK [lindex $paths 0]]
    if {![string is double -strict $slack] || [catch {expr {abs(double($slack)) < Inf}} finite] || !$finite || $slack < 0} {
        error "Invalid or negative $kind timing slack: $slack"
    }
}
foreach violation [get_drc_violations] {
    set severity [string toupper [get_property SEVERITY $violation]]
    if {$severity ni {WARNING ADVISORY INFO}} { error "Blocking DRC: $violation ($severity)" }
}
if {$emit} { write_bitstream -force [file join $out tiny_gpu_demo.bit] }
puts "Reports: $out; bitstream emitted=$emit; no programming performed"
