from abc import abstractproperty

from .util import get_ineg, get_oneg
from ..hdl import *
from ..lib.cdc import ResetSynchronizer
from ..build import *


__all__ = ["Xilinx7SeriesPlatform"]


class Xilinx7SeriesPlatform(TemplatedPlatform):
    """
    Vivado toolchain
    ----------------

    Required tools:
        * ``vivado``

    The environment is populated by running the script specified in the environment variable
    ``NMIGEN_ENV_Vivado``, if present.

    Available overrides:
        * ``script_after_read``: inserts commands after ``read_xdc`` in Tcl script.
        * ``script_after_synth``: inserts commands after ``synth_design`` in Tcl script.
        * ``script_after_place``: inserts commands after ``place_design`` in Tcl script.
        * ``script_after_route``: inserts commands after ``route_design`` in Tcl script.
        * ``script_before_bitstream``: inserts commands before ``write_bitstream`` in Tcl script.
        * ``script_after_bitstream``: inserts commands after ``write_bitstream`` in Tcl script.
        * ``add_constraints``: inserts commands in XDC file.
        * ``vivado_opts``: adds extra options for ``vivado``.

    Build products:
        * ``{{name}}.log``: Vivado log.
        * ``{{name}}_timing_synth.rpt``: Vivado report.
        * ``{{name}}_utilization_hierarchical_synth.rpt``: Vivado report.
        * ``{{name}}_utilization_synth.rpt``: Vivado report.
        * ``{{name}}_utilization_hierarchical_place.rpt``: Vivado report.
        * ``{{name}}_utilization_place.rpt``: Vivado report.
        * ``{{name}}_io.rpt``: Vivado report.
        * ``{{name}}_control_sets.rpt``: Vivado report.
        * ``{{name}}_clock_utilization.rpt``:  Vivado report.
        * ``{{name}}_route_status.rpt``: Vivado report.
        * ``{{name}}_drc.rpt``: Vivado report.
        * ``{{name}}_methodology.rpt``: Vivado report.
        * ``{{name}}_timing.rpt``: Vivado report.
        * ``{{name}}_power.rpt``: Vivado report.
        * ``{{name}}_route.dcp``: Vivado design checkpoint.
        * ``{{name}}.bit``: binary bitstream with metadata.
        * ``{{name}}.bin``: binary bitstream.

    Symbiflow toolchain
    -------------------

    Required tools:
        * ``synth``
        * ``pack``
        * ``place``
        * ``route``
        * ``write_fasm``
        * ``write_bitstream``

    The environment is populated by running the script specified in the environment variable
    ``NMIGEN_ENV_Symbiflow``, if present.

    Available overrides:
        * ``add_constraints``: inserts commands in XDC file.
    """

    toolchain = None # selected when creating platform

    device  = abstractproperty()
    package = abstractproperty()
    speed   = abstractproperty()

    @property
    def _part(self):
        return "{}{}-{}".format(self.device, self.package, self.speed)

    # Vivado templates

    _vivado_required_tools = ["vivado"]
    _vivado_file_templates = {
        **TemplatedPlatform.build_script_templates,
        "build_{{name}}.sh": r"""
            # {{autogenerated}}
            set -e{{verbose("x")}}
            if [ -z "$BASH" ] ; then exec /bin/bash "$0" "$@"; fi
            [ -n "${{platform._toolchain_env_var}}" ] && . "${{platform._toolchain_env_var}}"
            {{emit_commands("sh")}}
        """,
        "{{name}}.v": r"""
            /* {{autogenerated}} */
            {{emit_verilog()}}
        """,
        "{{name}}.debug.v": r"""
            /* {{autogenerated}} */
            {{emit_debug_verilog()}}
        """,
        "{{name}}.tcl": r"""
            # {{autogenerated}}
            create_project -force -name {{name}} -part {{platform._part}}
            {% for file in platform.iter_extra_files(".v", ".sv", ".vhd", ".vhdl") -%}
                add_files {{file|tcl_escape}}
            {% endfor %}
            add_files {{name}}.v
            read_xdc {{name}}.xdc
            {% for file in platform.iter_extra_files(".xdc") -%}
                read_xdc {{file|tcl_escape}}
            {% endfor %}
            {{get_override("script_after_read")|default("# (script_after_read placeholder)")}}
            synth_design -top {{name}}
            foreach cell [get_cells -quiet -hier -filter {nmigen.vivado.false_path == "TRUE"}] {
                set_false_path -to $cell
            }
            foreach cell [get_cells -quiet -hier -filter {nmigen.vivado.max_delay != ""}] {
                set clock [get_clocks -of_objects \
                    [all_fanin -flat -startpoints_only [get_pin $cell/D]]]
                if {[llength $clock] != 0} {
                    set_max_delay -datapath_only -from $clock \
                        -to [get_cells $cell] [get_property nmigen.vivado.max_delay $cell]
                }
            }
            {{get_override("script_after_synth")|default("# (script_after_synth placeholder)")}}
            report_timing_summary -file {{name}}_timing_synth.rpt
            report_utilization -hierarchical -file {{name}}_utilization_hierachical_synth.rpt
            report_utilization -file {{name}}_utilization_synth.rpt
            opt_design
            place_design
            {{get_override("script_after_place")|default("# (script_after_place placeholder)")}}
            report_utilization -hierarchical -file {{name}}_utilization_hierarchical_place.rpt
            report_utilization -file {{name}}_utilization_place.rpt
            report_io -file {{name}}_io.rpt
            report_control_sets -verbose -file {{name}}_control_sets.rpt
            report_clock_utilization -file {{name}}_clock_utilization.rpt
            route_design
            {{get_override("script_after_route")|default("# (script_after_route placeholder)")}}
            phys_opt_design
            report_timing_summary -no_header -no_detailed_paths
            write_checkpoint -force {{name}}_route.dcp
            report_route_status -file {{name}}_route_status.rpt
            report_drc -file {{name}}_drc.rpt
            report_methodology -file {{name}}_methodology.rpt
            report_timing_summary -datasheet -max_paths 10 -file {{name}}_timing.rpt
            report_power -file {{name}}_power.rpt
            {{get_override("script_before_bitstream")|default("# (script_before_bitstream placeholder)")}}
            write_bitstream -force -bin_file {{name}}.bit
            {{get_override("script_after_bitstream")|default("# (script_after_bitstream placeholder)")}}
            quit
        """,
        "{{name}}.xdc": r"""
            # {{autogenerated}}
            {% for port_name, pin_name, attrs in platform.iter_port_constraints_bits() -%}
                set_property LOC {{pin_name}} [get_ports {{port_name|tcl_escape}}]
                {% for attr_name, attr_value in attrs.items() -%}
                    set_property {{attr_name}} {{attr_value|tcl_escape}} [get_ports {{port_name|tcl_escape}}]
                {% endfor %}
            {% endfor %}
            {% for net_signal, port_signal, frequency in platform.iter_clock_constraints() -%}
                {% if port_signal is not none -%}
                    create_clock -name {{port_signal.name|ascii_escape}} -period {{1000000000/frequency}} [get_ports {{port_signal.name|tcl_escape}}]
                {% else -%}
                    create_clock -name {{net_signal.name|ascii_escape}} -period {{1000000000/frequency}} [get_nets {{net_signal|hierarchy("/")|tcl_escape}}]
                {% endif %}
            {% endfor %}
            {{get_override("add_constraints")|default("# (add_constraints placeholder)")}}
        """
    }
    _vivado_command_templates = [
        r"""
        {{invoke_tool("vivado")}}
            {{verbose("-verbose")}}
            {{get_override("vivado_opts")|options}}
            -mode batch
            -log {{name}}.log
            -source {{name}}.tcl
        """
    ]

    # Symbiflow templates

    _symbiflow_part_map = {
        "xc7a35ticsg324-1L": "xc7a35tcsg324-1", # Arty-A7
    }

    _symbiflow_required_tools = [
        "synth",
        "pack",
        "place",
        "route",
        "write_fasm",
        "write_bitstream"
    ]
    _symbiflow_file_templates = {
        **TemplatedPlatform.build_script_templates,
        "{{name}}.v": r"""
            /* {{autogenerated}} */
            {{emit_verilog()}}
        """,
        "{{name}}.debug.v": r"""
            /* {{autogenerated}} */
            {{emit_debug_verilog()}}
        """,
        "{{name}}.pcf": r"""
            # {{autogenerated}}
            {% for port_name, pin_name, attrs in platform.iter_port_constraints_bits() -%}
                set_io {{port_name}} {{pin_name}}
            {% endfor %}
        """,
        "{{name}}.xdc": r"""
            # {{autogenerated}}
            {% for port_name, pin_name, attrs in platform.iter_port_constraints_bits() -%}
                {% for attr_name, attr_value in attrs.items() -%}
                    set_property {{attr_name}} {{attr_value}} [get_ports {{port_name|tcl_escape}} }]
                {% endfor %}
            {% endfor %}
            {{get_override("add_constraints")|default("# (add_constraints placeholder)")}}
        """,
        "{{name}}.sdc": r"""
            # {{autogenerated}}
            {% for net_signal, port_signal, frequency in platform.iter_clock_constraints() -%}
                {% if port_signal is none -%}
                    create_clock -period {{1000000000/frequency}} {{net_signal.name|ascii_escape}}
                {% endif %}
            {% endfor %}
        """
    }
    _symbiflow_command_templates = [
        r"""
        {{invoke_tool("synth")}}
            -t {{name}}
            -v {% for file in platform.iter_extra_files(".v", ".sv", ".vhd", ".vhdl") -%} {{file}} {% endfor %} {{name}}.v
            -p {{platform._symbiflow_part_map.get(platform._part, platform._part)}}
            -x {{name}}.xdc
        """,
        r"""
        {{invoke_tool("pack")}}
            -e {{name}}.eblif
            -P {{platform._symbiflow_part_map.get(platform._part, platform._part)}}
            -s {{name}}.sdc
        """,
        r"""
        {{invoke_tool("place")}}
            -e {{name}}.eblif
            -p {{name}}.pcf
            -n {{name}}.net
            -P {{platform._symbiflow_part_map.get(platform._part, platform._part)}}
            -s {{name}}.sdc
        """,
        r"""
        {{invoke_tool("route")}}
            -e {{name}}.eblif
            -P {{platform._symbiflow_part_map.get(platform._part, platform._part)}}
            -s {{name}}.sdc
        """,
        r"""
        {{invoke_tool("write_fasm")}}
            -e {{name}}.eblif
            -P {{platform._symbiflow_part_map.get(platform._part, platform._part)}}
        """,
        r"""
        {{invoke_tool("write_bitstream")}}
            -f {{name}}.fasm
            -p {{platform._symbiflow_part_map.get(platform._part, platform._part)}}
            -b {{name}}.bit
        """
    ]

    # Common logic

    def __init__(self, *, toolchain="Vivado"):
        super().__init__()

        assert toolchain in ("Vivado", "Symbiflow")
        self.toolchain = toolchain

    @property
    def required_tools(self):
        if self.toolchain == "Vivado":
            return self._vivado_required_tools
        if self.toolchain == "Symbiflow":
            return self._symbiflow_required_tools
        assert False

    @property
    def file_templates(self):
        if self.toolchain == "Vivado":
            return self._vivado_file_templates
        if self.toolchain == "Symbiflow":
            return self._symbiflow_file_templates
        assert False

    @property
    def command_templates(self):
        if self.toolchain == "Vivado":
            return self._vivado_command_templates
        if self.toolchain == "Symbiflow":
            return self._symbiflow_command_templates
        assert False

    def create_missing_domain(self, name):
        # Xilinx devices have a global write enable (GWE) signal that asserted during configuraiton
        # and deasserted once it ends. Because it is an asynchronous signal (GWE is driven by logic
        # syncronous to configuration clock, which is not used by most designs), even though it is
        # a low-skew global network, its deassertion may violate a setup/hold constraint with
        # relation to a user clock. The recommended solution is to use a BUFGCE driven by the EOS
        # signal. For details, see:
        #   * https://www.xilinx.com/support/answers/44174.html
        #   * https://www.xilinx.com/support/documentation/white_papers/wp272.pdf
        if name == "sync" and self.default_clk is not None:
            clk_i = self.request(self.default_clk).i
            if self.default_rst is not None:
                rst_i = self.request(self.default_rst).i

            m = Module()

            if self.toolchain == "Vivado":
                ready = Signal()
                m.submodules += Instance("STARTUPE2", o_EOS=ready)
                m.domains += ClockDomain("sync", reset_less=self.default_rst is None)
                # Actually use BUFGCTRL configured as BUFGCE, since using BUFGCE causes
                # sim/synth mismatches with Vivado 2019.2, and the suggested workaround
                # (SIM_DEVICE parameter) breaks Vivado 2017.4.
                m.submodules += Instance("BUFGCTRL",
                    p_SIM_DEVICE="7SERIES",
                    i_I0=clk_i,   i_S0=C(1, 1), i_CE0=ready,   i_IGNORE0=C(0, 1),
                    i_I1=C(1, 1), i_S1=C(0, 1), i_CE1=C(0, 1), i_IGNORE1=C(1, 1),
                    o_O=ClockSignal("sync")
                )
            elif self.toolchain == "Symbiflow":
                cd_sync = ClockDomain("sync", reset_less=self.default_rst is None)
                m.domains += cd_sync
                m.submodules += Instance("BUFG", i_I=clk_i, o_O=cd_sync.clk)
                self.add_clock_constraint(cd_sync.clk, self.default_clk_frequency)
            else:
                assert False

            if self.default_rst is not None:
                m.submodules.reset_sync = ResetSynchronizer(rst_i, domain="sync")
            return m

    def add_clock_constraint(self, clock, frequency):
        super().add_clock_constraint(clock, frequency)
        clock.attrs["keep"] = "TRUE"

    def _get_xdr_buffer(self, m, pin, *, i_invert=None, o_invert=None):
        def get_dff(clk, d, q):
            # SDR I/O is performed by packing a flip-flop into the pad IOB.
            for bit in range(len(q)):
                m.submodules += Instance("FDCE",
                    a_IOB="TRUE",
                    i_C=clk,
                    i_CE=Const(1),
                    i_CLR=Const(0),
                    i_D=d[bit],
                    o_Q=q[bit]
                )

        def get_iddr(clk, d, q1, q2):
            for bit in range(len(q1)):
                m.submodules += Instance("IDDR",
                    p_DDR_CLK_EDGE="SAME_EDGE_PIPELINED",
                    p_SRTYPE="ASYNC",
                    p_INIT_Q1=0, p_INIT_Q2=0,
                    i_C=clk,
                    i_CE=Const(1),
                    i_S=Const(0), i_R=Const(0),
                    i_D=d[bit],
                    o_Q1=q1[bit], o_Q2=q2[bit]
                )

        def get_oddr(clk, d1, d2, q):
            for bit in range(len(q)):
                m.submodules += Instance("ODDR",
                    p_DDR_CLK_EDGE="SAME_EDGE",
                    p_SRTYPE="ASYNC",
                    p_INIT=0,
                    i_C=clk,
                    i_CE=Const(1),
                    i_S=Const(0), i_R=Const(0),
                    i_D1=d1[bit], i_D2=d2[bit],
                    o_Q=q[bit]
                )

        if "i" in pin.dir:
            assert i_invert is not None
            if pin.xdr < 2:
                pin_i  = get_ineg(m, pin.i,  i_invert)
            elif pin.xdr == 2:
                pin_i0 = get_ineg(m, pin.i0, i_invert)
                pin_i1 = get_ineg(m, pin.i1, i_invert)
        if "o" in pin.dir:
            assert o_invert is not None
            if pin.xdr < 2:
                pin_o  = get_oneg(m, pin.o,  o_invert)
            elif pin.xdr == 2:
                pin_o0 = get_oneg(m, pin.o0, o_invert)
                pin_o1 = get_oneg(m, pin.o1, o_invert)

        i = o = t = None
        if "i" in pin.dir:
            i = Signal(pin.width, name="{}_xdr_i".format(pin.name))
        if "o" in pin.dir:
            o = Signal(pin.width, name="{}_xdr_o".format(pin.name))
        if pin.dir in ("oe", "io"):
            t = Signal(1,         name="{}_xdr_t".format(pin.name))

        if pin.xdr == 0:
            if "i" in pin.dir:
                i = pin_i
            if "o" in pin.dir:
                o = pin_o
            if pin.dir in ("oe", "io"):
                t = ~pin.oe
        elif pin.xdr == 1:
            if "i" in pin.dir:
                get_dff(pin.i_clk, i, pin_i)
            if "o" in pin.dir:
                get_dff(pin.o_clk, pin_o, o)
            if pin.dir in ("oe", "io"):
                get_dff(pin.o_clk, ~pin.oe, t)
        elif pin.xdr == 2:
            if "i" in pin.dir:
                get_iddr(pin.i_clk, i, pin_i0, pin_i1)
            if "o" in pin.dir:
                get_oddr(pin.o_clk, pin_o0, pin_o1, o)
            if pin.dir in ("oe", "io"):
                get_dff(pin.o_clk, ~pin.oe, t)
        else:
            assert False

        return (i, o, t)

    def get_input(self, pin, port, attrs, invert):
        self._check_feature("single-ended input", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert)
        for bit in range(pin.width):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("IBUF",
                i_I=port.io[bit],
                o_O=i[bit]
            )
        return m

    def get_output(self, pin, port, attrs, invert):
        self._check_feature("single-ended output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        if self.toolchain == "Vivado":
            for bit in range(pin.width):
                m.submodules["{}_{}".format(pin.name, bit)] = Instance("OBUF",
                    i_I=o[bit],
                    o_O=port.io[bit]
                )
        elif self.toolchain == "Symbiflow":
            m.d.comb += port.eq(self._invert_if(invert, o))
        else:
            assert False
        return m

    def get_tristate(self, pin, port, attrs, invert):
        if self.toolchain == "Symbiflow":
            return super().get_tristate(pin, port, attrs, invert)

        self._check_feature("single-ended tristate", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        for bit in range(pin.width):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("OBUFT",
                i_T=t,
                i_I=o[bit],
                o_O=port.io[bit]
            )
        return m

    def get_input_output(self, pin, port, attrs, invert):
        if self.toolchain == "Symbiflow":
            return super().get_input_output(pin, port, attrs, invert)

        self._check_feature("single-ended input/output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert, o_invert=invert)
        for bit in range(pin.width):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("IOBUF",
                i_T=t,
                i_I=o[bit],
                o_O=i[bit],
                io_IO=port.io[bit]
            )
        return m

    def get_diff_input(self, pin, port, attrs, invert):
        if self.toolchain == "Symbiflow":
            return super().get_diff_input(pin, port, attrs, invert)

        self._check_feature("differential input", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert)
        for bit in range(pin.width):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("IBUFDS",
                i_I=port.p[bit], i_IB=port.n[bit],
                o_O=i[bit]
            )
        return m

    def get_diff_output(self, pin, port, attrs, invert):
        if self.toolchain == "Symbiflow":
            return super().get_diff_output(pin, port, attrs, invert)

        self._check_feature("differential output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        for bit in range(pin.width):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("OBUFDS",
                i_I=o[bit],
                o_O=port.p[bit], o_OB=port.n[bit]
            )
        return m

    def get_diff_tristate(self, pin, port, attrs, invert):
        if self.toolchain == "Symbiflow":
            return super().get_diff_tristate(pin, port, attrs, invert)

        self._check_feature("differential tristate", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        for bit in range(pin.width):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("OBUFTDS",
                i_T=t,
                i_I=o[bit],
                o_O=port.p[bit], o_OB=port.n[bit]
            )
        return m

    def get_diff_input_output(self, pin, port, attrs, invert):
        if self.toolchain == "Symbiflow":
            return super().get_diff_input_output(pin, port, attrs, invert)

        self._check_feature("differential input/output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert, o_invert=invert)
        for bit in range(pin.width):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("IOBUFDS",
                i_T=t,
                i_I=o[bit],
                o_O=i[bit],
                io_IO=port.p[bit], io_IOB=port.n[bit]
            )
        return m

    # The synchronizer implementations below apply two separate but related timing constraints.
    #
    # First, the ASYNC_REG attribute prevents inference of shift registers from synchronizer FFs,
    # and constraints the FFs to be placed as close as possible, ideally in one CLB. This attribute
    # only affects the synchronizer FFs themselves.
    #
    # Second, the nmigen.vivado.false_path or nmigen.vivado.max_delay attribute affects the path
    # into the synchronizer. If maximum input delay is specified, a datapath-only maximum delay
    # constraint is applied, limiting routing delay (and therefore skew) at the synchronizer input.
    # Otherwise, a false path constraint is used to omit the input path from the timing analysis.

    def get_ff_sync(self, ff_sync):
        m = Module()
        flops = [Signal(ff_sync.i.shape(), name="stage{}".format(index),
                        reset=ff_sync._reset, reset_less=ff_sync._reset_less,
                        attrs={"ASYNC_REG": "TRUE"})
                 for index in range(ff_sync._stages)]
        if ff_sync._max_input_delay is None:
            flops[0].attrs["nmigen.vivado.false_path"] = "TRUE"
        else:
            flops[0].attrs["nmigen.vivado.max_delay"] = str(ff_sync._max_input_delay * 1e9)
        for i, o in zip((ff_sync.i, *flops), flops):
            m.d[ff_sync._o_domain] += o.eq(i)
        m.d.comb += ff_sync.o.eq(flops[-1])
        return m

    def get_async_ff_sync(self, async_ff_sync):
        m = Module()
        m.domains += ClockDomain("async_ff", async_reset=True, local=True)
        flops = [Signal(1, name="stage{}".format(index), reset=1,
                        attrs={"ASYNC_REG": "TRUE"})
                 for index in range(async_ff_sync._stages)]
        if async_ff_sync._max_input_delay is None:
            flops[0].attrs["nmigen.vivado.false_path"] = "TRUE"
        else:
            flops[0].attrs["nmigen.vivado.max_delay"] = str(async_ff_sync._max_input_delay * 1e9)
        for i, o in zip((0, *flops), flops):
            m.d.async_ff += o.eq(i)

        if async_ff_sync._edge == "pos":
            m.d.comb += ResetSignal("async_ff").eq(async_ff_sync.i)
        else:
            m.d.comb += ResetSignal("async_ff").eq(~async_ff_sync.i)

        m.d.comb += [
            ClockSignal("async_ff").eq(ClockSignal(async_ff_sync._o_domain)),
            async_ff_sync.o.eq(flops[-1])
        ]

        return m
