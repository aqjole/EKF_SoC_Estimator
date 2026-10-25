function ekf = ekf_update(ekf, i_a, v_v, t_degc)
  % Correct x and P with the voltage v_v measured at current i_a (Eq. 8 to Eq. 11), as Ekf.update.
  % OCV, dOCV/dSoC and R0 are read at the prior SoC. P_post is formed before the SoC limit needs it.
  soc_prior = ekf.x(1);
  v1_prior = ekf.x(2);
  v2_prior = ekf.x(3);
  ocv = ekf_lookup(ekf, 'ocv', t_degc, soc_prior);
  docv = ekf_lookup(ekf, 'docv', t_degc, soc_prior);
  r0 = ekf_lookup(ekf, 'r0', t_degc, soc_prior);

  y_hat = ocv - v1_prior - v2_prior - r0 * i_a;  % Eq. 8
  H = [docv, -1, -1];  % Eq. 8, dR0/dSoC left out

  P_Ht = ekf.P * H';
  S = H * P_Ht + ekf.cfg.r;  % Eq. 9
  K = P_Ht / S;  % Eq. 9

  innovation = v_v - y_hat;
  x_post = ekf.x + K * innovation;  % Eq. 10

  I_KH = eye(3) - K * H;
  I_KH_P = I_KH * ekf.P;
  K_R_Kt = ekf.cfg.r * (K * K');
  P_post = I_KH_P * I_KH' + K_R_Kt;  % Eq. 11

  ekf.x = limit_soc(x_post, P_post);  % Eq. 10, the SoC limit
  ekf.P = P_post;
end
