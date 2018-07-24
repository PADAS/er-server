-- This version takes in a single PID value as an integer
CREATE OR REPLACE FUNCTION get_cpu_mem(INT)
RETURNS TABLE(PID INT, CPU_percent float, MEM_percent float) AS
$body$
  my $ps = "ps --no-headers -up ".$_[0];
  my $awk = "awk '{print \$2\":\"\$3\":\"\$4}'";
  my $cmd = $ps."|".$awk;
  $output = `$cmd 2>&1`;
  my @line = split(/:/,$output);
  return_next {'pid' => $line[0],'cpu_percent' => $line[1], 'mem_percent' => $line[2]};
$body$
LANGUAGE plperlu;

-- This version accept in a comma-separated list of pids
CREATE OR REPLACE FUNCTION get_cpu_mem(TEXT)
RETURNS TABLE(PID INT, CPU_percent float, MEM_percent float) AS
$body$
  my $ps = "ps --no-headers -up ".$_[0];
  my $awk = "awk '{print \$2\":\"\$3\":\"\$4}'";
  my $cmd = $ps."|".$awk;
  $output = `$cmd 2>&1`;
  @output = split(/[\n\r]+/,$output);
  foreach $out (@output)
  {
    my @line = split(/:/,$out);
    return_next{'pid' => $line[0],'cpu_percent' => $line[1], 'mem_percent' => $line[2]};
  }
  return undef;
$body$
LANGUAGE plperlu;
