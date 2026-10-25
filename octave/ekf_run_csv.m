% Run the filter over a CSV of filter inputs and write the SoC of every row, as c/tools/ekf_run_csv.c.
%
% usage:  octave-cli <repo>/octave/ekf_run_csv.m <in.csv> <out.csv> <q_soc> <q_v> <r> <soc0>
%
% The tables come from results/params.csv of this repository. in.csv names the columns dt_s, i_a, v_v
% and t_degc in its header (read_inputs); its first row has dt_s = 0, so predict leaves the state
% unchanged there. out.csv gets a header "soc" and one SoC per input row with 17 significant digits.
% P0 has the standard deviations 0.2 (SoC) and 0.05 V (V1, V2), the defaults of EkfConfig.

octave_dir = fileparts(mfilename('fullpath'));
addpath(octave_dir);

args = argv();
if numel(args) ~= 6
  error('usage: ekf_run_csv.m <in.csv> <out.csv> <q_soc> <q_v> <r> <soc0>');
end
settings = str2double(args(3:6));
if ~all(isfinite(settings))
  error('q_soc, q_v, r and soc0 must be finite numbers');
end

params = read_params(fullfile(fileparts(octave_dir), 'results', 'params.csv'));
inputs = read_inputs(args{1});
cfg = struct('q_soc', settings(1), 'q_v', settings(2), 'r', settings(3), 'p0_soc_std', 0.2, 'p0_v_std', 0.05);

ekf = ekf_init(params, cfg, settings(4));
n = rows(inputs);
soc = zeros(n, 1);
for k = 1:n
  [ekf, soc(k)] = ekf_step(ekf, inputs(k, 2), inputs(k, 3), inputs(k, 4), inputs(k, 1));
end

fid = fopen(args{2}, 'w');
if fid < 0
  error('%s: cannot write', args{2});
end
fprintf(fid, 'soc\n');
fprintf(fid, '%.17g\n', soc);
if fclose(fid) ~= 0
  error('%s: cannot write', args{2});
end
