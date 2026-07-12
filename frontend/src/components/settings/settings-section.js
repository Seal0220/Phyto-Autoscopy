import SettingsField from "@/components/settings/settings-field";
import SubsectionHeader from "@/components/ui/subsection-header";
import { sectionMeta } from "@/lib/settings";

export default function SettingsSection({
  group,
  section,
  leaves,
  onChange,
}) {
  if (group === "cameras") {
    const enabledLeaves = leaves.filter((leaf) => leaf.path.at(-1) === "enabled");
    const inputLeaves = leaves.filter((leaf) => leaf.path.at(-1) !== "enabled");

    return (
      <section className="grid min-w-0 content-start gap-3 border-b border-white/10 px-3 py-5 last:border-b-0 min-[720px]:border-r min-[720px]:nth-[2n]:border-r-0 min-[1180px]:border-b-0 min-[1180px]:nth-[2n]:border-r min-[1180px]:nth-[3n]:border-r-0">
        {enabledLeaves.map((leaf) => (
          <SettingsField
            key={leaf.path.join(".")}
            group={group}
            leaf={leaf}
            onChange={onChange}
          />
        ))}
        <div className="grid grid-cols-1 gap-3 min-[520px]:grid-cols-2 min-[1600px]:grid-cols-3">
          {inputLeaves.map((leaf) => (
            <SettingsField
              key={leaf.path.join(".")}
              group={group}
              leaf={leaf}
              onChange={onChange}
            />
          ))}
        </div>
      </section>
    );
  }

  const meta = sectionMeta(group, section);
  return (
    <section className="grid min-w-0 content-start gap-5">
      <SubsectionHeader
        title={meta.title}
        description={meta.description}
      />
      <div className="grid gap-3">
        {leaves.map((leaf) => (
          <SettingsField
            key={leaf.path.join(".")}
            group={group}
            leaf={leaf}
            onChange={onChange}
          />
        ))}
      </div>
    </section>
  );
}
