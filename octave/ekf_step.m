function [ekf, soc] = ekf_step(ekf, i_a, v_v, t_degc, dt_s)
  % One sample, as Ekf.step: predict over dt_s with the previous sample's current, then update with
  % this sample's current i_a, which is then held over the next step. Returns the posterior SoC.
  ekf = ekf_predict(ekf, ekf.i_held, t_degc, dt_s);
  ekf = ekf_update(ekf, i_a, v_v, t_degc);
  ekf.i_held = i_a;
  soc = ekf.x(1);
end
