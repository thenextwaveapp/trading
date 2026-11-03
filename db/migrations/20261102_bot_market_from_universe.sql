-- A bot derives its market from its universe — the universe is the single
-- source of truth for "what market is this". pf_bots.market is a denormalized
-- convenience column (Leaderboard/Market filters); this trigger keeps it equal
-- to the bot's universe market so the two can never diverge. Fixes the class of
-- bug where a bot was labelled one market while its universe (and trades) were
-- another (e.g. "USDJPY London Short": market=crypto, universe=fx_spot).

create or replace function pf_set_bot_market() returns trigger as $$
begin
  if new.universe_id is not null then
    select market into new.market from pf_universes where id = new.universe_id;
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists pf_bot_market on pf_bots;
create trigger pf_bot_market
  before insert or update on pf_bots
  for each row execute function pf_set_bot_market();

-- One-time resync of existing drift (incl. the stocks->equity vocab mismatch).
update pf_bots b set market = u.market
from pf_universes u
where b.universe_id = u.id and b.market is distinct from u.market;
