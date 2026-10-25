function ekf = ekf_predict(ekf, i_held, t_degc, dt_s)
  % Move x and P over a step of dt_s with i_held held over it (Eq. 6, Eq. 7), as Ekf.predict.
  % R1, tau1, R2, tau2 are read at the previous posterior SoC. dt_s = 0 leaves x and P unchanged.
  soc = ekf.x(1);
  r1 = ekf_lookup(ekf, 'r1', t_degc, soc);
  tau1 = ekf_lookup(ekf, 'tau1', t_degc, soc);
  r2 = ekf_lookup(ekf, 'r2', t_degc, soc);
  tau2 = ekf_lookup(ekf, 'tau2', t_degc, soc);

  a1 = exp(-dt_s / tau1);
  a2 = exp(-dt_s / tau2);
  F = diag([1, a1, a2]);
  B = [-dt_s / (3600 * ekf.q_ref_ah); r1 * (1 - a1); r2 * (1 - a2)];
  Q = diag([ekf.cfg.q_soc, ekf.cfg.q_v, ekf.cfg.q_v]) * dt_s;

  ekf.x = F * ekf.x + B * i_held;  % Eq. 6
  F_P = F * ekf.P;
  ekf.P = F_P * F' + Q;  % Eq. 7
end
