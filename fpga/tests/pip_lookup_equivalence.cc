// Compare an isolated nextpnr lookup candidate with the pinned linear lookup.
// This diagnostic is not a substitute for nextpnr's complete --test.
#include "nextpnr.h"
#include <cstdint>
#include <iostream>
#include <vector>

USING_NEXTPNR_NAMESPACE

static PipId reference(const Context &ctx, int tile, IdStringList name)
{
    const auto &tdata = chip_tile_info(ctx.chip_info, tile);
    for (int pip = 0; pip < tdata.pips.ssize(); pip++) {
        if (IdString(tdata.wires[tdata.pips[pip].dst_wire].name) == name[1] &&
            IdString(tdata.wires[tdata.pips[pip].src_wire].name) == name[2]) {
            const auto tmp_pip = PipId(tile, pip);
            if ((name.size() == 3 && !ctx.isPipInverting(tmp_pip)) ||
                (name.size() == 4 && ctx.isPipInverting(tmp_pip)))
                return tmp_pip;
        }
    }
    return PipId();
}

static IdStringList name3(IdString tile, IdString dst, IdString src)
{
    return IdStringList::concat(tile, IdStringList::concat(dst, src));
}

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    ArchArgs args;
    args.device = argv[1];
    args.chipdb_override = argv[2];
    Context ctx(args);
    ctx.uarch->init(&ctx);
    ctx.late_init();
    const auto *chip = ctx.chip_info;
    std::vector<int> representative(chip->tile_types.size(), -1);
    for (int tile = 0; tile < chip->tile_insts.ssize(); ++tile) {
        int type = chip->tile_insts[tile].type;
        if (representative.at(type) == -1) representative[type] = tile;
    }
    const auto inv = ctx.id("INV");
    const auto missing = ctx.id("__tinygpu_missing_lookup_wire__");
    uint64_t comparisons = 0, pips = 0, types = 0;
    for (int tile : representative) {
        if (tile < 0) continue;
        ++types;
        const auto &td = chip_tile_info(chip, tile);
        for (int pip = 0; pip < td.pips.ssize(); ++pip) {
            ++pips;
            auto native_name = ctx.getPipName(PipId(tile, pip));
            auto plain = name3(native_name[0], native_name[1], native_name[2]);
            auto reversed = name3(native_name[0], native_name[2], native_name[1]);
            std::vector<IdStringList> cases = {
                plain, IdStringList::concat(plain, inv),
                reversed, IdStringList::concat(reversed, inv),
                name3(native_name[0], missing, native_name[2]),
                name3(native_name[0], native_name[1], missing)};
            for (const auto &name : cases) {
                auto expected = reference(ctx, tile, name);
                auto actual = ctx.getPipByName(name);
                if (expected != actual) {
                    std::cerr << "FAIL lookup equivalence: " << name.str(&ctx)
                              << " expected=" << expected.tile << ":" << expected.index
                              << " actual=" << actual.tile << ":" << actual.index << "\n";
                    return 1;
                }
                ++comparisons;
            }
            if (ctx.getPipByName(cases[4]) != PipId() || ctx.getPipByName(cases[5]) != PipId()) {
                std::cerr << "FAIL missing wire lookup\n";
                return 1;
            }
        }
    }
    std::cout << "PASS lookup equivalence: " << types << " represented tile types, "
              << pips << " type-level pips, " << comparisons << " comparisons\n";
    std::cout << "Full native architecture integrity remains required.\n";
    return 0;
}
