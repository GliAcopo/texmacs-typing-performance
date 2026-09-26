;; Keystroke latency benchmark, loaded with: texmacs <doc.tm> -x '(load "keystroke.scm")'
;; Each step presses one key from a delayed command and then pauses TMBENCH_GAP ms, so every
;; key gets its own GUI update cycle (typeset + repaint). The cycle times themselves are logged
;; by the instrumented texmacs.bin (TEXMACS_BENCH_LOG); this file only records the window.
;; Env: TMBENCH_N (measured keys), TMBENCH_WARM, TMBENCH_POS (start|par|end), TMBENCH_OUT (file),
;;      TMBENCH_KEYS (comma separated keys, cycled; e.g. "a,b,space" or "a,a,a,return").
;;      TMBENCH_EXPR (scheme expression run per step instead of a key, e.g. "(make 'equation)").
;; POS par = end of the first plain-text paragraph of the body (after doc-data, toc, ...).
(define bench-n    (string->number (or (getenv "TMBENCH_N") "40")))
(define bench-warm (string->number (or (getenv "TMBENCH_WARM") "5")))
(define bench-pos  (or (getenv "TMBENCH_POS") "start"))
(define bench-out  (or (getenv "TMBENCH_OUT") "/tmp/tmbench.txt"))
(define bench-gap  (string->number (or (getenv "TMBENCH_GAP") "150")))
(define bench-t0 #f)
(define bench-expr (let ((e (getenv "TMBENCH_EXPR"))) (and e (string->object e))))
(define bench-keys (list->vector (string-split (or (getenv "TMBENCH_KEYS") "a") #\,)))

(define (bench-first-par)
  (let loop ((i 0))
    (let ((body (buffer-tree)))
      (if (>= i (tree-arity body)) #f
          (let ((t (tree-ref body i)))
            (if (or (and (tree-atomic? t) (> (string-length (tree->string t)) 20))
                    (tree-is? t 'concat))
                t
                (loop (+ i 1))))))))
(define bench-samples '())
(define bench-count 0)

(define (bench-finish)
  (call-with-output-file bench-out
    (lambda (port)
      (format port "~a ~a~%" bench-t0 (texmacs-time))
      (for-each (lambda (x) (format port "~a~%" x)) (reverse bench-samples))))
  (buffer-pretend-saved (current-buffer))
  (quit-TeXmacs))

(define (bench-step)
  (let ((now (texmacs-time)))
    (if (and (not bench-t0) (> bench-count bench-warm)) (set! bench-t0 now))
    (if (> bench-count (+ bench-n bench-warm))
        (begin (bench-finish) #t)
        (let ((k (vector-ref bench-keys (modulo bench-count (vector-length bench-keys)))))
          (if bench-expr (eval bench-expr) (key-press k))
          ;; samples = duration of the key-press call itself (scheme handlers + edit), ms
          (if (> bench-count bench-warm)
              (set! bench-samples (cons (- (texmacs-time) now) bench-samples)))
          (set! bench-count (+ bench-count 1))
          bench-gap))))

(define bench-tracing #f)
(define bench-mode (or (getenv "TMBENCH_MODE") "scheme"))
(define bench-ready (or (getenv "TMBENCH_READY") "/tmp/tmbench.ready"))
(define bench-done  (or (getenv "TMBENCH_DONE") "/tmp/tmbench.done"))

;; mode "xtest": position the cursor, signal readiness, let an external driver send real X key
;; events, and quit once the driver creates the done file. Writes the edited paragraph to OUT.
(if (getenv "TMBENCH_PROBE") (load (string-append (getenv "TMBENCH_DIR") "/probe.scm")))

(define (bench-wait-done)
  (if (not (file-exists? bench-done)) 200
      (begin
        (call-with-output-file bench-out
          (lambda (port) (format port "~a~%" (tree->string (cursor-tree)))))
        (buffer-pretend-saved (current-buffer))
        (quit-TeXmacs)
        #t)))

(delayed
  (:pause 3000)
  (cond ((== bench-pos "end") (go-end))
        ((== bench-pos "par") (let ((t (bench-first-par))) (if t (tree-go-to t :end) (go-start))))
        (else (go-start)))
  (if (== bench-mode "xtest")
      (begin
        (if (defined? 'probe-on) (set! probe-on #t))
        (set! bench-tracing #t)
        (call-with-output-file bench-ready (lambda (port) (format port "~a~%" (texmacs-time))))
        (exec-delayed-pause bench-wait-done))
      (exec-delayed-pause bench-step)))
